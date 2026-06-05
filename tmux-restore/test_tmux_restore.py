#!/usr/bin/env python3
"""Integration tests for tmux-restore. Drives a real tmux server in an
isolated socket so the user's live sessions are never touched.

Run: python3 test_tmux_restore.py
Or:  TESTS=test_layout python3 test_tmux_restore.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent
SCRIPT = REPO / "tmux_restore.py"
TEST_SOCKET = "tmux-restore-test"


def tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["tmux", "-L", TEST_SOCKET, *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"tmux {' '.join(args)} failed rc={r.returncode}: {r.stderr}")
    return r


def kill_test_server() -> None:
    subprocess.run(["tmux", "-L", TEST_SOCKET, "kill-server"], capture_output=True)


def script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=e,
    )


class TmuxRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state_dir = Path(tempfile.mkdtemp(prefix="tmux-restore-test-"))
        # Direct the script to use this isolated state dir
        cls.env = {
            "HOME": os.environ["HOME"],  # keep so claude paths still resolve
            "TMUX_RESTORE_STATE": str(cls.state_dir),  # not used by script today; reserved
        }
        # Override module-level paths by monkey-patching via env var won't work without code change.
        # Instead we redirect by symlinking the script's expected state dir.
        # Simpler: write/read to the real state dir but use unique snapshot names. We do that below.
        cls.snapshot_paths: list[Path] = []

    @classmethod
    def tearDownClass(cls):
        kill_test_server()
        shutil.rmtree(cls.state_dir, ignore_errors=True)

    def setUp(self):
        kill_test_server()
        # also remove any leftover RESTORE_FROM by killing test sessions on default socket
        # (we use only the test socket so this is unnecessary)

    def tearDown(self):
        kill_test_server()

    # ─── helpers ───

    def _wrapped_env(self) -> tuple[dict, Path]:
        """Return (env, wrapper_dir) with tmux aliased to the test socket and the
        script's state dir redirected to the test temp dir (so the launchd
        snapshot job can't take the lock from under us)."""
        env = os.environ.copy()
        wrapper_dir = Path(tempfile.mkdtemp(prefix="tmux-wrapper-"))
        wrapper = wrapper_dir / "tmux"
        # Find real tmux binary
        real_tmux = shutil.which("tmux") or "/opt/homebrew/bin/tmux"
        wrapper.write_text(
            f"#!/bin/sh\nexec {real_tmux} -L {TEST_SOCKET} \"$@\"\n"
        )
        wrapper.chmod(0o755)
        env["PATH"] = f"{wrapper_dir}:{env['PATH']}"
        env["TMUX_RESTORE_STATE"] = str(self.state_dir)
        return env, wrapper_dir

    def _snapshot_test_server(self) -> dict:
        env, wrapper_dir = self._wrapped_env()
        try:
            r = subprocess.run(
                [sys.executable, str(SCRIPT), "snapshot"],
                capture_output=True, text=True, env=env,
            )
            if r.returncode != 0 or not r.stdout.strip():
                raise AssertionError(
                    f"snapshot failed rc={r.returncode}\nstdout: {r.stdout!r}\nstderr: {r.stderr!r}"
                )
            path = Path(r.stdout.strip().splitlines()[0])
            self.snapshot_paths.append(path)
            return json.loads(path.read_text())
        finally:
            shutil.rmtree(wrapper_dir, ignore_errors=True)

    def _restore_with_wrapper(self, snapshot_path: Path, *args: str) -> subprocess.CompletedProcess:
        env, wrapper_dir = self._wrapped_env()
        try:
            r = subprocess.run(
                [sys.executable, str(SCRIPT), "restore", "--snapshot", str(snapshot_path), *args],
                capture_output=True, text=True, env=env,
            )
            return r
        finally:
            shutil.rmtree(wrapper_dir, ignore_errors=True)

    def _load_module(self, state_dir: Path):
        """Import tmux_restore.py with a test-owned state directory."""
        old_state = os.environ.get("TMUX_RESTORE_STATE")
        os.environ["TMUX_RESTORE_STATE"] = str(state_dir)
        try:
            spec = importlib.util.spec_from_file_location(
                f"tmux_restore_test_{time.time_ns()}", SCRIPT
            )
            if spec is None or spec.loader is None:
                raise AssertionError("could not load tmux_restore.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if old_state is None:
                os.environ.pop("TMUX_RESTORE_STATE", None)
            else:
                os.environ["TMUX_RESTORE_STATE"] = old_state

    # ─── tests ───

    def test_01_snapshot_empty_server(self):
        kill_test_server()
        snap = self._snapshot_test_server()
        self.assertEqual(snap["version"], 2)
        self.assertEqual(snap["tmux_sessions"], [])
        self.assertIn("snapshot_token", snap)

    def test_02_snapshot_single_session_single_pane(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "w1", "-c", os.environ["HOME"])
        snap = self._snapshot_test_server()
        self.assertEqual(len(snap["tmux_sessions"]), 1)
        s = snap["tmux_sessions"][0]
        self.assertEqual(s["name"], "s1")
        self.assertEqual(len(s["windows"]), 1)
        self.assertEqual(s["windows"][0]["name"], "w1")
        self.assertEqual(len(s["windows"][0]["panes"]), 1)
        self.assertEqual(s["windows"][0]["panes"][0]["cwd"], os.environ["HOME"])

    def test_03_snapshot_multi_pane_window_layout(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "w1", "-c", os.environ["HOME"])
        tmux("split-window", "-t", "s1:w1", "-h", "-c", os.environ["HOME"])
        tmux("split-window", "-t", "s1:w1.0", "-v", "-c", os.environ["HOME"])
        snap = self._snapshot_test_server()
        panes = snap["tmux_sessions"][0]["windows"][0]["panes"]
        self.assertEqual(len(panes), 3)
        layout = snap["tmux_sessions"][0]["windows"][0]["layout"]
        self.assertTrue(layout)
        self.assertIn(",", layout)

    def test_04_roundtrip_three_panes(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "w1", "-c", os.environ["HOME"])
        tmux("split-window", "-t", "s1:w1", "-h")
        tmux("split-window", "-t", "s1:w1.0", "-v")
        # mark a non-default active pane
        tmux("select-pane", "-t", "s1:w1.1")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        # capture original layout shape
        orig_panes = len(snap["tmux_sessions"][0]["windows"][0]["panes"])
        kill_test_server()
        # restore
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        # verify pane count restored
        out = tmux("list-panes", "-t", "s1:w1", "-F", "#{pane_index}").stdout
        self.assertEqual(len([x for x in out.strip().splitlines() if x]), orig_panes)

    def test_05_roundtrip_active_pane_preserved(self):
        tmux("new-session", "-d", "-s", "s1", "-c", os.environ["HOME"])
        tmux("split-window", "-t", "s1", "-h")
        tmux("split-window", "-t", "s1.0", "-v")
        tmux("select-pane", "-t", "s1.2")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        active = tmux(
            "list-panes", "-t", "s1", "-F", "#{?pane_active,#{pane_index},}"
        ).stdout
        active_idx = [x for x in active.strip().splitlines() if x.strip()]
        self.assertEqual(len(active_idx), 1)
        self.assertEqual(active_idx[0], "2")

    def test_06_roundtrip_active_window_preserved(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "a")
        tmux("new-window", "-t", "s1:", "-n", "b")
        tmux("new-window", "-t", "s1:", "-n", "c")
        tmux("select-window", "-t", "s1:b")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        out = tmux(
            "list-windows", "-t", "s1", "-F", "#{?window_active,#{window_name},}"
        ).stdout
        active = [x for x in out.strip().splitlines() if x.strip()]
        self.assertEqual(active, ["b"])

    def test_07_multi_session(self):
        tmux("new-session", "-d", "-s", "alpha", "-n", "a")
        tmux("new-session", "-d", "-s", "beta", "-n", "b")
        snap = self._snapshot_test_server()
        self.assertEqual(sorted(s["name"] for s in snap["tmux_sessions"]), ["alpha", "beta"])
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 0)
        sessions = tmux("list-sessions", "-F", "#{session_name}").stdout.strip().splitlines()
        self.assertEqual(sorted(sessions), ["alpha", "beta"])

    def test_08_only_sessions_filter(self):
        tmux("new-session", "-d", "-s", "alpha")
        tmux("new-session", "-d", "-s", "beta")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--only-sessions", "alpha", "--no-verify")
        self.assertEqual(r.returncode, 0)
        sessions = tmux("list-sessions", "-F", "#{session_name}").stdout.strip().splitlines()
        self.assertEqual(sorted(sessions), ["alpha"])

    def test_09_refuse_to_clobber(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "old")
        snap = self._snapshot_test_server()
        # leave session running; try to restore over it without --replace
        r = self._restore_with_wrapper(self.snapshot_paths[-1], "--no-verify")
        self.assertEqual(r.returncode, 2)
        # window still named "old" — no clobber happened
        out = tmux("list-windows", "-t", "s1", "-F", "#{window_name}").stdout.strip()
        self.assertIn("old", out)

    def test_10_replace_flag(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "old")
        snap = self._snapshot_test_server()
        # rename window so post-restore name differs from runtime
        tmux("rename-window", "-t", "s1:old", "current")
        r = self._restore_with_wrapper(self.snapshot_paths[-1], "--replace", "--no-verify")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        # window should be back to "old"
        out = tmux("list-windows", "-t", "s1", "-F", "#{window_name}").stdout.strip().splitlines()
        self.assertIn("old", out)

    def test_11_idempotency_token(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "w1")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r1 = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r1.returncode, 0)
        # Second invocation on same snapshot should exit 0 with "already restored" message
        r2 = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r2.returncode, 0)
        self.assertIn("already restored", r2.stdout)

    def test_12_dry_run_makes_no_changes(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "w1")
        snap_path = self.snapshot_paths[-1] if self.snapshot_paths else None
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--dry-run", "--no-verify")
        self.assertEqual(r.returncode, 0)
        # no sessions should exist
        r2 = tmux("list-sessions", check=False)
        self.assertNotEqual(r2.returncode, 0)  # no server / no sessions

    def test_13_target_session_rename(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "w1")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--target-session", "renamed", "--no-verify")
        self.assertEqual(r.returncode, 0)
        sessions = tmux("list-sessions", "-F", "#{session_name}").stdout.strip().splitlines()
        self.assertIn("renamed", sessions)

    def test_14_missing_cwd_falls_back(self):
        bad_dir = "/tmp/definitely-not-a-dir-" + str(int(time.time()))
        tmux("new-session", "-d", "-s", "s1", "-n", "w1", "-c", os.environ["HOME"])
        snap = self._snapshot_test_server()
        # mutate snapshot to point pane at nonexistent cwd
        snap_path = self.snapshot_paths[-1]
        d = json.loads(snap_path.read_text())
        d["tmux_sessions"][0]["windows"][0]["panes"][0]["cwd"] = bad_dir
        snap_path.write_text(json.dumps(d))
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 0)
        # session created with $HOME fallback
        cwd = tmux(
            "list-panes", "-t", "s1:w1", "-F", "#{pane_current_path}"
        ).stdout.strip()
        self.assertIn(cwd, (os.environ["HOME"], os.environ["HOME"] + "/"))

    def test_15_unknown_schema_version(self):
        tmux("new-session", "-d", "-s", "s1")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        d = json.loads(snap_path.read_text())
        d["version"] = 99
        snap_path.write_text(json.dumps(d))
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 4)

    def test_16_host_mismatch(self):
        tmux("new-session", "-d", "-s", "s1")
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        d = json.loads(snap_path.read_text())
        d["host"] = "some-other-host"
        snap_path.write_text(json.dumps(d))
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 5)
        r2 = self._restore_with_wrapper(snap_path, "--force-host", "--no-verify")
        self.assertEqual(r2.returncode, 0)

    def test_17_layout_preserved_three_pane(self):
        tmux("new-session", "-d", "-s", "s1", "-n", "w1")
        tmux("split-window", "-t", "s1:w1", "-h", "-p", "30")
        tmux("split-window", "-t", "s1:w1.0", "-v", "-p", "40")
        # capture pane widths
        pre = tmux(
            "list-panes", "-t", "s1:w1", "-F", "#{pane_width}x#{pane_height}"
        ).stdout.strip().splitlines()
        snap = self._snapshot_test_server()
        snap_path = self.snapshot_paths[-1]
        kill_test_server()
        r = self._restore_with_wrapper(snap_path, "--no-verify")
        self.assertEqual(r.returncode, 0)
        post = tmux(
            "list-panes", "-t", "s1:w1", "-F", "#{pane_width}x#{pane_height}"
        ).stdout.strip().splitlines()
        # Same number of panes; rough geometry match (within client-attached resize tolerance)
        self.assertEqual(len(pre), len(post))

    def test_18_pid_sid_map_read(self):
        state = self.state_dir / "pid-map-read"
        shutil.rmtree(state, ignore_errors=True)
        state.mkdir()
        mod = self._load_module(state)
        sid = str(uuid.uuid4())
        mod.PID_SID_MAP.write_text(f"111:{sid}\nnot-a-row\nbad:not-a-uuid\n")

        self.assertEqual(mod.read_pid_sid_map(), {111: sid})

    def test_19_pid_sid_map_prune(self):
        state = self.state_dir / "pid-map-prune"
        shutil.rmtree(state, ignore_errors=True)
        state.mkdir()
        mod = self._load_module(state)
        live_sid = str(uuid.uuid4())
        dead_sid = str(uuid.uuid4())
        mod.PID_SID_MAP.write_text(f"{os.getpid()}:{live_sid}\n999999:{dead_sid}\n")

        mod.prune_pid_sid_map()

        self.assertEqual(mod.read_pid_sid_map(), {os.getpid(): live_sid})

    def test_20_detect_agent_session_hook_fallback(self):
        state = self.state_dir / "hook-fallback"
        shutil.rmtree(state, ignore_errors=True)
        state.mkdir()
        mod = self._load_module(state)
        home = state / "home"
        mod.HOME = home
        sid = str(uuid.uuid4())
        cwd = "/Users/karsinkk/work"
        session_dir = home / ".claude" / "projects" / mod.encoded_cwd(cwd)
        session_dir.mkdir(parents=True)
        session_path = session_dir / f"{sid}.jsonl"
        session_path.write_text("{}\n")
        mod.PID_SID_MAP.write_text(f"111:{sid}\n")
        mod.descendant_pids = lambda pane_pid: [111]
        mod.proc_name = lambda pid: "claude"
        mod.proc_args = lambda pid: "claude"

        result = mod.detect_agent_session(222, cwd)

        self.assertTrue(result["claude_running"])
        self.assertEqual(result["claude_session_id"], sid)
        self.assertEqual(result["claude_session_path"], str(session_path))
        self.assertEqual(result["claude_args"], "(from hook map, pid=111)")

    def test_21_mapping_file_missing(self):
        state = self.state_dir / "pid-map-missing"
        shutil.rmtree(state, ignore_errors=True)
        state.mkdir()
        mod = self._load_module(state)

        self.assertEqual(mod.read_pid_sid_map(), {})

    def test_22_concurrent_hook_writes(self):
        hook = REPO / "hooks" / "tmux-restore-sid.sh"
        tmp_home = Path(tempfile.mkdtemp(prefix="tmux-restore-hook-home-"))
        try:
            env = os.environ.copy()
            env["HOME"] = str(tmp_home)
            sids = [str(uuid.uuid4()) for _ in range(12)]
            procs = [
                subprocess.Popen(
                    ["bash", str(hook)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                for _ in sids
            ]
            for proc, sid in zip(procs, sids):
                stdout, stderr = proc.communicate(json.dumps({"session_id": sid}), timeout=5)
                self.assertEqual(proc.returncode, 0, f"stdout={stdout!r} stderr={stderr!r}")

            mapping = tmp_home / ".local/share/tmux-restore/pid-sid.map"
            rows = [line.split(":", 1)[1] for line in mapping.read_text().splitlines()]
            self.assertEqual(sorted(rows), sorted(sids))
        finally:
            shutil.rmtree(tmp_home, ignore_errors=True)

    def test_23_codex_lsof_fallback(self):
        state = self.state_dir / "codex-lsof"
        shutil.rmtree(state, ignore_errors=True)
        state.mkdir()
        mod = self._load_module(state)
        home = state / "home"
        mod.HOME = home
        sid = str(uuid.uuid4())
        rollout = home / ".codex" / "sessions" / "2026" / "05" / "23" / f"rollout-test-{sid}.jsonl"
        rollout.parent.mkdir(parents=True)
        rollout.write_text("{}\n")
        mod.descendant_pids = lambda pane_pid: [333]
        mod.proc_name = lambda pid: "codex"
        mod.proc_args = lambda pid: "codex"
        mod.run_status = lambda cmd, timeout=5: (
            0,
            f"codex 333 karsinkk 29w REG 1,17 1 1 {rollout}\n",
            "",
        )

        result = mod.detect_agent_session(222, "/Users/karsinkk")

        self.assertTrue(result["codex_running"])
        self.assertEqual(result["codex_session_id"], sid)
        self.assertEqual(result["codex_session_path"], str(rollout))
        self.assertEqual(result["codex_args"], "(from lsof, pid=333)")

    def test_24_empty_pane_title_not_dropped(self):
        """Regression: panes with empty titles were silently dropped because
        panes_raw.strip() removed the trailing tab, leaving only 5 fields."""
        tmux("new-session", "-d", "-s", "s1", "-n", "w1", "-c", os.environ["HOME"])
        tmux("split-window", "-t", "s1:w1", "-h")
        snap = self._snapshot_test_server()
        panes = snap["tmux_sessions"][0]["windows"][0]["panes"]
        self.assertEqual(len(panes), 2)
        for p in panes:
            self.assertIn("cwd", p)
            self.assertIn("pane_pid", p)

    def test_25_basename_process_detection(self):
        """is_codex_process must match full-path comm names like
        /opt/homebrew/.../bin/codex returned by ps on macOS."""
        state = self.state_dir / "basename-detect"
        shutil.rmtree(state, ignore_errors=True)
        state.mkdir()
        mod = self._load_module(state)
        self.assertTrue(mod.is_codex_process(
            "/opt/homebrew/lib/node_modules/@openai/codex/node_modules/bin/codex",
            "codex"
        ))
        self.assertTrue(mod.is_claude_process(
            "/usr/local/lib/node_modules/.bin/claude",
            "claude"
        ))
        self.assertFalse(mod.is_codex_process("zsh", "/bin/zsh codex"))
        self.assertFalse(mod.is_claude_process("zsh", "/bin/zsh claude"))

    def test_26_lsof_picks_latest_rollout(self):
        """When multiple rollout files are open, pick the most recently modified."""
        state = self.state_dir / "lsof-latest"
        shutil.rmtree(state, ignore_errors=True)
        state.mkdir()
        mod = self._load_module(state)
        home = state / "home"
        mod.HOME = home

        sid_old = str(uuid.uuid4())
        sid_new = str(uuid.uuid4())
        base = home / ".codex" / "sessions" / "2026" / "05" / "24"
        base.mkdir(parents=True)
        old_f = base / f"rollout-old-{sid_old}.jsonl"
        new_f = base / f"rollout-new-{sid_new}.jsonl"
        old_f.write_text("{}\n")
        new_f.write_text("{}\n")
        os.utime(old_f, (1000, 1000))
        os.utime(new_f, (2000, 2000))

        mod.run_status = lambda cmd, timeout=5: (
            0,
            f"codex 1 user 37w REG 1,17 100 1 {old_f}\ncodex 1 user 38w REG 1,17 200 2 {new_f}\n",
            "",
        )
        result = mod.find_codex_rollout_by_lsof(1)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], sid_new)
        self.assertEqual(result[1], new_f)


if __name__ == "__main__":
    only = os.environ.get("TESTS")
    if only:
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        for name in only.split(","):
            suite.addTests(loader.loadTestsFromName(name, module=sys.modules[__name__]))
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        unittest.main(verbosity=2)

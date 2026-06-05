#!/usr/bin/env python3
"""tmux + claude/codex session snapshot and restore.

Captures every pane's cwd, command, and (when claude/codex is running) the
JSONL session file UUID by parsing the running process's argv. Restore replays
the layout, window and pane indices, and launches `claude --resume <sid>` /
`codex resume <sid>` per pane.

Subcommands: snapshot, restore, list, show, diff, verify.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

HOME = Path.home()
# Allow tests / alt configs to redirect state via env. Defaults preserve prod paths.
STATE_DIR = Path(os.environ.get("TMUX_RESTORE_STATE", str(HOME / ".local/share/tmux-restore")))
SNAPSHOT_DIR = STATE_DIR / "snapshots"
LATEST = SNAPSHOT_DIR / "latest.json"
LOG_FILE = STATE_DIR / "restore.log"
LOCK_FILE = STATE_DIR / ".snapshot.lock"
PID_SID_MAP = STATE_DIR / "pid-sid.map"
PID_SID_MAP_LOCK = STATE_DIR / "pid-sid.map.lock"

SCHEMA_VERSION = 2
SNAPSHOT_RETENTION_DAYS = 7
SNAPSHOT_MIN_KEEP = 50

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
CLAUDE_RESUME_ARG_RE = re.compile(
    r"(?:--resume|-r)\s+(" + UUID_RE.pattern + r")"
)
CODEX_RESUME_ARG_RE = re.compile(
    r"\bresume\b\s+(?:--last\s+)?(" + UUID_RE.pattern + r")"
)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{now_iso()}] {msg}\n")


def run_status(cmd: list[str], timeout: int = 5) -> tuple[int, str, str]:
    """Run command, return (returncode, stdout, stderr). Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 127, "", str(e)


def run(cmd: list[str], check: bool = True, timeout: int = 5) -> str:
    rc, out, err = run_status(cmd, timeout=timeout)
    if rc != 0 and check:
        raise subprocess.CalledProcessError(rc, cmd, out, err)
    return out


def tmux(*args: str, check: bool = True) -> str:
    return run(["tmux", *args], check=check)


def tmux_status(*args: str) -> tuple[int, str, str]:
    return run_status(["tmux", *args])


# ───────────────────────── snapshot ─────────────────────────


def descendant_pids(root_pid: int, max_depth: int = 4) -> list[int]:
    """All descendant PIDs of root_pid up to max_depth."""
    found: list[int] = []
    frontier = [root_pid]
    for _ in range(max_depth):
        next_frontier: list[int] = []
        for pid in frontier:
            rc, out, _ = run_status(["pgrep", "-P", str(pid)])
            if rc not in (0, 1):  # 1 = no matches, not an error
                continue
            for line in out.strip().splitlines():
                try:
                    child = int(line.strip())
                    found.append(child)
                    next_frontier.append(child)
                except ValueError:
                    continue
        if not next_frontier:
            break
        frontier = next_frontier
    return found


def proc_name(pid: int) -> str:
    rc, out, _ = run_status(["ps", "-p", str(pid), "-o", "comm="])
    return out.strip() if rc == 0 else ""


def proc_args(pid: int) -> str:
    rc, out, _ = run_status(["ps", "-p", str(pid), "-o", "args="])
    return out.strip() if rc == 0 else ""


def _basename(name: str) -> str:
    return os.path.basename(name) if "/" in name else name


def is_claude_process(name: str, args: str) -> bool:
    base = _basename(name)
    if base == "claude":
        return True
    if base == "node" and ("claude" in args or "/.claude/" in args):
        return True
    return False


def is_codex_process(name: str, args: str) -> bool:
    base = _basename(name)
    if base == "codex":
        return True
    if base == "node" and "codex" in args:
        return True
    return False


def encoded_cwd(cwd: str) -> str:
    return cwd.replace("/", "-")


def find_claude_jsonl_by_uuid(sid: str, cwd: str) -> Path | None:
    path = HOME / ".claude" / "projects" / encoded_cwd(cwd) / f"{sid}.jsonl"
    if path.exists():
        return path
    projects = HOME / ".claude" / "projects"
    if not projects.is_dir():
        return None
    for proj in projects.glob("*"):
        candidate = proj / f"{sid}.jsonl"
        if candidate.exists():
            return candidate
    return None


def find_codex_rollout_by_uuid(sid: str) -> Path | None:
    base = HOME / ".codex" / "sessions"
    if not base.is_dir():
        return None
    for p in base.rglob(f"rollout-*-{sid}.jsonl"):
        return p
    return None


def find_codex_rollout_by_lsof(pid: int) -> tuple[str, Path] | None:
    rc, out, _ = run_status(["lsof", "-p", str(pid)])
    if rc != 0:
        return None
    pattern = re.compile(r"(/\S*?rollout-\S*?-(" + UUID_RE.pattern + r")\.jsonl)")
    best: tuple[str, Path, float] | None = None
    for line in out.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        path = Path(m.group(1))
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if best is None or mtime > best[2]:
            best = (m.group(2), path, mtime)
    return (best[0], best[1]) if best else None


def read_pid_sid_map() -> dict[int, str]:
    """Read Claude PID -> session-id rows written by the SessionStart hook."""
    mapping: dict[int, str] = {}
    if not PID_SID_MAP.exists():
        return mapping
    try:
        PID_SID_MAP.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_SID_MAP_LOCK, "a") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_SH)
            with open(PID_SID_MAP) as f:
                for line in f:
                    line = line.strip()
                    if ":" not in line:
                        continue
                    pid_s, sid = line.split(":", 1)
                    if not UUID_RE.fullmatch(sid):
                        continue
                    try:
                        mapping[int(pid_s)] = sid
                    except ValueError:
                        continue
    except OSError:
        pass
    return mapping


def prune_pid_sid_map() -> None:
    """Remove hook-map rows whose PID no longer exists."""
    if not PID_SID_MAP.exists():
        return
    try:
        PID_SID_MAP.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_SID_MAP_LOCK, "a") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            live: dict[int, str] = {}
            with open(PID_SID_MAP) as f:
                for line in f:
                    line = line.strip()
                    if ":" not in line:
                        continue
                    pid_s, sid = line.split(":", 1)
                    if not UUID_RE.fullmatch(sid):
                        continue
                    try:
                        pid = int(pid_s)
                        os.kill(pid, 0)
                    except (ValueError, ProcessLookupError):
                        continue
                    except PermissionError:
                        pass
                    live[pid] = sid
            tmp = PID_SID_MAP.with_suffix(".map.tmp")
            with open(tmp, "w") as f:
                for pid, sid in sorted(live.items()):
                    f.write(f"{pid}:{sid}\n")
            os.replace(tmp, PID_SID_MAP)
    except OSError:
        pass


def detect_agent_session(pane_pid: int, pane_cwd: str) -> dict[str, Any]:
    """Capture per-pane agent session UUIDs from argv and verified runtime state.

    Claude fresh sessions are recovered from the SessionStart hook's PID map.
    Codex fresh sessions are recovered only when the running process holds its
    rollout JSONL open. Cwd/mtime guessing is intentionally not used because
    panes sharing a cwd can collide.
    """
    result: dict[str, Any] = {
        "claude_session_id": None,
        "claude_session_path": None,
        "claude_session_mtime": None,
        "claude_args": None,
        "claude_running": False,
        "codex_session_id": None,
        "codex_session_path": None,
        "codex_session_mtime": None,
        "codex_args": None,
        "codex_running": False,
    }
    child_pids = descendant_pids(pane_pid)
    claude_pids: list[int] = []
    codex_pids: list[int] = []
    for pid in child_pids:
        name = proc_name(pid)
        args = proc_args(pid)
        if is_claude_process(name, args):
            result["claude_running"] = True
            claude_pids.append(pid)
            if not result["claude_session_id"]:
                m = CLAUDE_RESUME_ARG_RE.search(args)
                sid = m.group(1) if m else None
                if sid:
                    path = find_claude_jsonl_by_uuid(sid, pane_cwd)
                    result["claude_session_id"] = sid
                    result["claude_args"] = args
                    if path:
                        result["claude_session_path"] = str(path)
                        try:
                            result["claude_session_mtime"] = dt.datetime.fromtimestamp(
                                path.stat().st_mtime
                            ).astimezone().isoformat(timespec="seconds")
                        except OSError:
                            pass
        elif is_codex_process(name, args):
            result["codex_running"] = True
            codex_pids.append(pid)
            if not result["codex_session_id"]:
                m = CODEX_RESUME_ARG_RE.search(args)
                sid = m.group(1) if m else None
                if sid:
                    path = find_codex_rollout_by_uuid(sid)
                    result["codex_session_id"] = sid
                    result["codex_args"] = args
                    if path:
                        result["codex_session_path"] = str(path)
                        try:
                            result["codex_session_mtime"] = dt.datetime.fromtimestamp(
                                path.stat().st_mtime
                            ).astimezone().isoformat(timespec="seconds")
                        except OSError:
                            pass
    if result["claude_running"] and not result["claude_session_id"]:
        pid_map = read_pid_sid_map()
        for pid in claude_pids:
            sid = pid_map.get(pid)
            if not sid:
                continue
            path = find_claude_jsonl_by_uuid(sid, pane_cwd)
            if not path:
                # Subagent sessions fire SessionStart but store their transcript
                # inside the parent's JSONL. Skip SIDs with no own JSONL file.
                continue
            result["claude_session_id"] = sid
            result["claude_args"] = f"(from hook map, pid={pid})"
            result["claude_session_path"] = str(path)
            try:
                result["claude_session_mtime"] = dt.datetime.fromtimestamp(
                    path.stat().st_mtime
                ).astimezone().isoformat(timespec="seconds")
            except OSError:
                pass
            break
    if result["codex_running"] and not result["codex_session_id"]:
        for pid in codex_pids:
            found = find_codex_rollout_by_lsof(pid)
            if not found:
                continue
            sid, path = found
            result["codex_session_id"] = sid
            result["codex_args"] = f"(from lsof, pid={pid})"
            result["codex_session_path"] = str(path)
            try:
                result["codex_session_mtime"] = dt.datetime.fromtimestamp(
                    path.stat().st_mtime
                ).astimezone().isoformat(timespec="seconds")
            except OSError:
                pass
            break
    return result


def tmux_global_options() -> dict[str, str]:
    """Capture base-index / pane-base-index so restore can map snapshot
    indices onto the running server's numbering scheme."""
    opts = {}
    for key in ("base-index", "pane-base-index"):
        rc, out, _ = tmux_status("show-options", "-gv", key)
        opts[key] = out.strip() if rc == 0 and out.strip() else "0"
    return opts


def snapshot_tmux() -> dict[str, Any]:
    rc, server_out, _ = tmux_status("list-sessions", "-F", "#{session_name}\t#{?session_attached,1,0}")
    base = {
        "version": SCHEMA_VERSION,
        "snapshot_time": now_iso(),
        "host": socket.gethostname(),
        # snapshot_token is set after the file path is known (see cmd_snapshot)
        # so it's stable across processes that re-read the same file.
        "tmux_options": tmux_global_options() if rc == 0 else {},
        "tmux_sessions": [],
    }
    if rc != 0 or not server_out.strip():
        return base

    sessions = []
    for sess_line in server_out.strip().splitlines():
        parts = sess_line.split("\t")
        if not parts:
            continue
        sess_name = parts[0].strip()
        attached = (len(parts) > 1 and parts[1].strip() == "1")
        if not sess_name:
            continue
        win_fmt = (
            "#{window_index}\t#{window_name}\t#{?window_active,1,0}\t#{window_layout}"
        )
        windows_raw = tmux("list-windows", "-t", sess_name, "-F", win_fmt, check=False)
        windows = []
        for line in windows_raw.splitlines():
            line = line.rstrip("\n\r")
            wparts = line.split("\t")
            if len(wparts) < 4:
                continue
            w_idx, w_name, w_active, w_layout = wparts
            pane_fmt = (
                "#{pane_index}\t#{?pane_active,1,0}\t#{pane_current_path}"
                "\t#{pane_current_command}\t#{pane_pid}\t#{pane_title}"
            )
            panes_raw = tmux(
                "list-panes", "-t", f"{sess_name}:{w_idx}", "-F", pane_fmt, check=False
            )
            panes = []
            for pline in panes_raw.splitlines():
                pline = pline.rstrip("\n\r")
                pparts = pline.split("\t", 5)
                if len(pparts) < 5:
                    continue
                p_title = pparts[5] if len(pparts) > 5 else ""
                p_idx, p_active, p_cwd, p_cmd, p_pid_s = pparts[:5]
                try:
                    p_pid = int(p_pid_s)
                except ValueError:
                    continue
                agent = detect_agent_session(p_pid, p_cwd)
                panes.append({
                    "index": int(p_idx),
                    "active": p_active == "1",
                    "cwd": p_cwd,
                    "command": p_cmd,
                    "title": p_title,
                    "pane_pid": p_pid,
                    **agent,
                })
            windows.append({
                "index": int(w_idx),
                "name": w_name,
                "active": w_active == "1",
                "layout": w_layout,
                "panes": panes,
            })
        sessions.append({"name": sess_name, "attached": attached, "windows": windows})
    base["tmux_sessions"] = sessions
    return base


def atomic_write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_latest_symlink(target_name: str) -> None:
    tmp_link = SNAPSHOT_DIR / "latest.json.tmp"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    os.symlink(target_name, tmp_link)
    os.replace(tmp_link, LATEST)


def prune_snapshots() -> None:
    if not SNAPSHOT_DIR.exists():
        return
    files = sorted(
        [p for p in SNAPSHOT_DIR.glob("*.json") if p.name != "latest.json"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    cutoff = time.time() - SNAPSHOT_RETENTION_DAYS * 86400
    for i, p in enumerate(files):
        if i < SNAPSHOT_MIN_KEEP:
            continue
        if p.stat().st_mtime < cutoff:
            try:
                p.unlink()
            except OSError:
                pass


def cmd_snapshot(args: argparse.Namespace) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.touch(exist_ok=True)
    with open(LOCK_FILE, "w") as lockf:
        try:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if not args.quiet:
                print("Another snapshot in progress; skipping.", file=sys.stderr)
            return 0
        data = snapshot_tmux()
        ts = dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        out_path = SNAPSHOT_DIR / f"{ts}.json"
        # Deterministic token: stable for the same snapshot file regardless of how
        # many times it's read. Prevents idempotency from breaking when the
        # launchd job re-snapshots between two restore invocations.
        data["snapshot_token"] = out_path.stem  # e.g. "2026-05-21T22-30-00"
        atomic_write_json(data, out_path)
        update_latest_symlink(out_path.name)
        prune_snapshots()
        prune_pid_sid_map()
        n_sessions = len(data["tmux_sessions"])
        n_panes = sum(
            len(w["panes"]) for s in data["tmux_sessions"] for w in s["windows"]
        )
        n_claude = sum(
            1
            for s in data["tmux_sessions"]
            for w in s["windows"]
            for p in w["panes"]
            if p.get("claude_session_id")
        )
        n_codex = sum(
            1
            for s in data["tmux_sessions"]
            for w in s["windows"]
            for p in w["panes"]
            if p.get("codex_session_id")
        )
        log(
            f"snapshot wrote {out_path.name} token={data['snapshot_token'][:8]} "
            f"sessions={n_sessions} panes={n_panes} claude={n_claude} codex={n_codex}"
        )
        if not args.quiet:
            print(f"{out_path}")
            print(
                f"sessions={n_sessions} panes={n_panes} "
                f"claude_sids={n_claude} codex_sids={n_codex}"
            )
        return 0


# ───────────────────────── restore ─────────────────────────


def session_exists(name: str) -> bool:
    rc, _, _ = tmux_status("has-session", "-t", f"={name}")
    return rc == 0


def get_restore_token(session: str) -> str | None:
    rc, out, _ = tmux_status("show-environment", "-t", session, "RESTORE_FROM")
    if rc != 0:
        return None
    s = out.strip()
    # tmux returns "-RESTORE_FROM" when variable is unset, "RESTORE_FROM=value" otherwise.
    if not s or s.startswith("-"):
        return None
    if "=" in s:
        return s.split("=", 1)[1]
    return None


def set_restore_token(session: str, token: str) -> None:
    tmux_status("set-environment", "-t", session, "RESTORE_FROM", token)


def resolve_snapshot(arg: str | None) -> Path:
    if arg:
        # try as-is, as basename in snapshot dir, with .json suffix added
        candidates = [Path(arg).expanduser()]
        candidates.append(SNAPSHOT_DIR / arg)
        if not arg.endswith(".json"):
            candidates.append(SNAPSHOT_DIR / f"{arg}.json")
        for c in candidates:
            if c.exists():
                return c
        raise FileNotFoundError(f"snapshot not found: {arg}")
    if LATEST.is_symlink():
        target = os.readlink(LATEST)
        candidate = SNAPSHOT_DIR / target if not os.path.isabs(target) else Path(target)
        if candidate.exists():
            return candidate
    if LATEST.is_file():
        return LATEST
    files = sorted(
        [p for p in SNAPSHOT_DIR.glob("*.json") if p.name != "latest.json"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if files:
        return files[0]
    raise FileNotFoundError("no snapshots found in " + str(SNAPSHOT_DIR))


def valid_cwd(p: str) -> str:
    if p and Path(p).is_dir():
        return p
    log(f"cwd {p!r} missing; falling back to $HOME")
    return str(HOME)


def shell_quote_for_send_keys(s: str) -> str:
    # send-keys takes literal keystrokes; we pass the command as a single arg, no quoting needed
    return s


def restore_pane_command(p: dict) -> str | None:
    """Resolve the command to send-keys into a pane on restore.

    Priority:
      1. claude_session_id (definite SID from argv) → `claude --resume <sid>`
      2. claude_running (had live claude, no SID) → `claude`
      3. codex_session_id → `codex resume <sid>`
      4. codex_running → `codex`
      5. otherwise: do nothing (leave the pane at the shell prompt).

    Note: `command` is the foreground process name at snapshot time. For claude
    that's the pane title (e.g. `2.1.146`), not a reliable signal. We trust the
    descendant-process scan in detect_agent_session() instead.
    """
    claude_sid = p.get("claude_session_id")
    claude_path = p.get("claude_session_path")
    if claude_sid:
        if claude_path and not Path(claude_path).exists():
            log(f"claude session {claude_sid} JSONL missing; launching plain claude")
            return "claude"
        if not claude_path:
            # SID from hook map with no recorded path — verify JSONL exists at
            # restore time. Subagent SIDs have no own JSONL and would fail.
            resolved = find_claude_jsonl_by_uuid(claude_sid, p.get("cwd", ""))
            if not resolved:
                log(f"claude session {claude_sid} has no JSONL (likely subagent); launching plain claude")
                return "claude"
        return f"claude --resume {claude_sid}"
    if p.get("claude_running"):
        return "claude"
    codex_sid = p.get("codex_session_id")
    codex_path = p.get("codex_session_path")
    if codex_sid:
        if codex_path and not Path(codex_path).exists():
            log(f"codex session {codex_sid} rollout missing; launching plain codex")
            return "codex"
        return f"codex resume {codex_sid}"
    if p.get("codex_running"):
        return "codex"
    return None


# Default-ish pane titles we should NOT restore (tmux sets these automatically)
_DEFAULT_TITLE_HOSTNAME = socket.gethostname()


def should_restore_title(title: str, command: str) -> bool:
    if not title:
        return False
    if title == command:
        return False
    if title == _DEFAULT_TITLE_HOSTNAME or title == _DEFAULT_TITLE_HOSTNAME.split(".")[0]:
        return False
    # tmux's default pane title format is often the hostname; also "zsh" or shell name
    if title in ("zsh", "bash", "fish", "sh"):
        return False
    return True


def restore_session(
    sess: dict,
    target_name: str,
    replace: bool,
    dry_run: bool,
    snapshot_token: str,
    base_index_delta: tuple[int, int],
) -> int:
    """base_index_delta: (window_delta, pane_delta) = current - snapshot."""
    name = target_name
    if session_exists(name):
        existing_token = get_restore_token(name)
        if existing_token == snapshot_token and not replace:
            print(f"[{name}] already restored from snapshot {snapshot_token[:8]}; skipping.")
            return 0
        if not replace:
            if dry_run:
                print(f"DRY [{name}] would refuse to clobber (existing session); add --replace.")
                return 0
            print(
                f"[{name}] tmux session already exists; refuse to clobber. "
                f"Re-run with --replace or --target-session <new>.",
                file=sys.stderr,
            )
            return 2
        if not dry_run:
            tmux_status("kill-session", "-t", name)
        else:
            print(f"DRY kill-session -t {name}")

    windows = sorted(sess["windows"], key=lambda w: w["index"])
    if not windows:
        print(f"[{name}] no windows in snapshot; skipping.")
        return 0

    w_delta, p_delta = base_index_delta
    first_w = windows[0]
    first_pane_cwd = (
        valid_cwd(first_w["panes"][0]["cwd"]) if first_w["panes"] else str(HOME)
    )
    if dry_run:
        print(f"DRY new-session -d -s {name} -n {first_w['name']} -c {first_pane_cwd}")
    else:
        rc, _, err = tmux_status(
            "new-session", "-d", "-s", name, "-n", first_w["name"], "-c", first_pane_cwd
        )
        if rc != 0:
            print(f"[{name}] new-session failed: {err.strip()}", file=sys.stderr)
            return 6

    # Build name → snapshot active pane index map, for select-pane after restoration
    active_pane_for_window: dict[str, int] = {}
    active_window: str | None = None

    for i, w in enumerate(windows):
        wname = w["name"]
        panes = sorted(w["panes"], key=lambda p: p["index"])
        # Map snapshot pane index → runtime absolute index after creation
        # Strategy: snapshot's first pane index becomes the window's pane-base-index;
        # subsequent panes get successive indices via split-window in sorted order.
        snap_first_idx = panes[0]["index"] if panes else 0
        # runtime layout: panes created in order will be assigned indices [base, base+1, ...]
        # so the runtime index for the j-th pane (sorted) is (current pane-base-index) + j
        # We don't need to compute per-pane delta — we always reference by ordinal.
        if w.get("active"):
            active_window = wname

        if i == 0:
            pass  # already created via new-session
        else:
            cwd0 = valid_cwd(panes[0]["cwd"]) if panes else str(HOME)
            if dry_run:
                print(f"DRY new-window -d -t {name}: -n {wname} -c {cwd0}")
            else:
                rc, _, err = tmux_status(
                    "new-window", "-d", "-t", f"{name}:", "-n", wname, "-c", cwd0
                )
                if rc != 0:
                    print(f"[{name}:{wname}] new-window failed: {err.strip()}", file=sys.stderr)

        # split-window once per additional pane, in snapshot order
        for j in range(1, len(panes)):
            cwd = valid_cwd(panes[j]["cwd"])
            if dry_run:
                print(f"DRY split-window -t {name}:{wname} -c {cwd}")
            else:
                tmux_status("split-window", "-t", f"{name}:{wname}", "-c", cwd)

        # Apply saved layout. tmux's `select-layout` accepts the full layout string
        # (with leading checksum). On failure we fall back to a deterministic tiled layout.
        layout = w.get("layout")
        if layout and not dry_run:
            rc, _, err = tmux_status("select-layout", "-t", f"{name}:{wname}", layout)
            if rc != 0:
                log(f"layout apply failed for {name}:{wname} ({err.strip()}); using tiled")
                if len(panes) > 1:
                    tmux_status("select-layout", "-t", f"{name}:{wname}", "tiled")
        elif dry_run and layout:
            print(f"DRY select-layout -t {name}:{wname} {layout[:32]}...")

        # Read back actual runtime pane indices in creation order, so we can target them precisely.
        actual_indices: list[int] = []
        if not dry_run:
            rc, out, _ = tmux_status("list-panes", "-t", f"{name}:{wname}", "-F", "#{pane_index}")
            if rc == 0:
                actual_indices = [int(x) for x in out.strip().splitlines() if x.strip().isdigit()]

        # Find the snapshot's active pane (positional index within the sorted list)
        active_pos = next((k for k, p in enumerate(panes) if p.get("active")), 0)
        if active_pos < len(actual_indices):
            active_pane_for_window[wname] = actual_indices[active_pos]
        elif actual_indices:
            active_pane_for_window[wname] = actual_indices[0]

        # send-keys per pane in snapshot order, mapped to actual runtime indices
        time.sleep(0.15)
        for k, p in enumerate(panes):
            runtime_idx = actual_indices[k] if k < len(actual_indices) else p["index"]
            target = f"{name}:{wname}.{runtime_idx}"
            cmd = restore_pane_command(p)
            if should_restore_title(p.get("title", ""), p.get("command", "")):
                if dry_run:
                    print(f"DRY select-pane -t {target} -T {p['title']!r}")
                else:
                    tmux_status("select-pane", "-t", target, "-T", p["title"])
            if cmd:
                if dry_run:
                    print(f"DRY send-keys -t {target} {cmd!r} Enter")
                else:
                    tmux_status("send-keys", "-t", target, cmd, "Enter")
                    time.sleep(0.3)

    # Restore active pane within each window
    if not dry_run:
        for wname, pidx in active_pane_for_window.items():
            tmux_status("select-pane", "-t", f"{name}:{wname}.{pidx}")
        if active_window:
            tmux_status("select-window", "-t", f"{name}:{active_window}")
        set_restore_token(name, snapshot_token)
        log(f"restored session {name} from snapshot token {snapshot_token}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    try:
        snap_path = resolve_snapshot(args.snapshot)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 8
    with open(snap_path) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"error: snapshot {snap_path} is not valid JSON: {e}", file=sys.stderr)
            return 9
    if data.get("version") not in (1, SCHEMA_VERSION):
        print(f"snapshot version {data.get('version')} not supported (this tool is v{SCHEMA_VERSION})", file=sys.stderr)
        return 4
    if data.get("host") != socket.gethostname() and not args.force_host:
        print(
            f"snapshot host {data.get('host')} != {socket.gethostname()}; use --force-host",
            file=sys.stderr,
        )
        return 5
    age = time.time() - snap_path.stat().st_mtime
    if age > SNAPSHOT_RETENTION_DAYS * 86400 and not args.force:
        print(
            f"snapshot is {age / 86400:.1f}d old (>{SNAPSHOT_RETENTION_DAYS}d); use --force",
            file=sys.stderr,
        )
        return 3

    tmux_status("start-server")
    snapshot_token = data.get("snapshot_token") or "legacy-" + os.path.basename(snap_path).replace(".json", "")

    # Compute base-index delta between snapshot and runtime
    snap_opts = data.get("tmux_options", {}) or {}
    snap_w_base = int(snap_opts.get("base-index", "0"))
    snap_p_base = int(snap_opts.get("pane-base-index", "0"))
    cur_opts = tmux_global_options()
    cur_w_base = int(cur_opts.get("base-index", "0"))
    cur_p_base = int(cur_opts.get("pane-base-index", "0"))
    delta = (cur_w_base - snap_w_base, cur_p_base - snap_p_base)
    if delta != (0, 0):
        log(f"base-index delta: window {delta[0]:+d}, pane {delta[1]:+d}")

    only = set(args.only_sessions.split(",")) if args.only_sessions else None
    rc = 0
    for sess in data.get("tmux_sessions", []):
        sess_name = sess["name"]
        if only and sess_name not in only:
            continue
        target = args.target_session or sess_name
        r = restore_session(sess, target, args.replace, args.dry_run, snapshot_token, delta)
        if r:
            rc = r
    if not args.dry_run and not args.no_verify and rc == 0:
        rc_v = verify_restoration(data, only, args.target_session)
        if rc_v:
            rc = rc_v
    return rc


# ───────────────────────── verify ─────────────────────────


def verify_restoration(data: dict, only: set[str] | None, target_override: str | None) -> int:
    """Compare runtime tmux state against the snapshot. Returns 0 if all panes match."""
    mismatches = []
    for sess in data.get("tmux_sessions", []):
        sess_name = sess["name"]
        if only and sess_name not in only:
            continue
        target = target_override or sess_name
        if not session_exists(target):
            mismatches.append(f"session {target} missing")
            continue
        snap_windows = {w["name"]: w for w in sess["windows"]}
        rc, out, _ = tmux_status("list-windows", "-t", target, "-F", "#{window_name}")
        runtime_windows = [w for w in out.strip().splitlines() if w]
        for wname in snap_windows:
            if wname not in runtime_windows:
                mismatches.append(f"window {target}:{wname} missing")
                continue
            snap_pane_count = len(snap_windows[wname]["panes"])
            rc, pout, _ = tmux_status(
                "list-panes", "-t", f"{target}:{wname}", "-F", "#{pane_index}"
            )
            runtime_pane_count = len([x for x in pout.strip().splitlines() if x])
            if runtime_pane_count != snap_pane_count:
                mismatches.append(
                    f"{target}:{wname} pane count {runtime_pane_count} != {snap_pane_count}"
                )
            # Check claude args on agent panes
            for k, p in enumerate(sorted(snap_windows[wname]["panes"], key=lambda x: x["index"])):
                if not p.get("claude_session_id") and not p.get("codex_session_id"):
                    continue
                rc, ppids, _ = tmux_status(
                    "list-panes", "-t", f"{target}:{wname}", "-F", "#{pane_pid}"
                )
                pid_lines = [x for x in ppids.strip().splitlines() if x]
                if k >= len(pid_lines):
                    continue
                pane_pid = int(pid_lines[k])
                # Wait briefly for claude/codex to spawn
                expected_sid = p.get("claude_session_id") or p.get("codex_session_id")
                found = False
                for _ in range(8):
                    for child in descendant_pids(pane_pid):
                        if expected_sid in proc_args(child):
                            found = True
                            break
                    if not found:
                        pid_map = read_pid_sid_map()
                        for child in descendant_pids(pane_pid):
                            if pid_map.get(child) == expected_sid:
                                found = True
                                break
                    if found:
                        break
                    time.sleep(0.5)
                if not found:
                    mismatches.append(
                        f"{target}:{wname}.{k} expected sid {expected_sid} not in descendant args or hook map"
                    )
    if mismatches:
        print("verification mismatches:", file=sys.stderr)
        for m in mismatches:
            print(f"  - {m}", file=sys.stderr)
        log("verify mismatches:\n  " + "\n  ".join(mismatches))
        return 7
    log("verify ok")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        snap_path = resolve_snapshot(args.snapshot)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 8
    with open(snap_path) as f:
        data = json.load(f)
    only = set(args.only_sessions.split(",")) if args.only_sessions else None
    return verify_restoration(data, only, args.target_session)


# ───────────────────────── list / show / diff ─────────────────────────


def cmd_list(args: argparse.Namespace) -> int:
    if not SNAPSHOT_DIR.exists():
        print("no snapshots")
        return 0
    files = sorted(SNAPSHOT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        if p.name == "latest.json":
            continue
        sz = p.stat().st_size
        mt = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{mt}  {sz:>7}  {p.name}")
    return 0


def _summarize_snapshot(path: Path) -> dict | None:
    """Return per-session/window/agent/project shape + a structural digest.

    Digest groups snapshots whose layout + agent placement + project cwds match,
    so long stable runs collapse into one row in `pick`.
    """
    try:
        d = json.load(open(path))
    except Exception:
        return None
    sessions = []
    shape: list = []
    for s in d.get("tmux_sessions", []):
        wins = []
        for w in s.get("windows", []):
            agents: list[str] = []
            projects: set[str] = set()
            sids: list[str] = []
            for p in w.get("panes", []):
                if p.get("claude_running"):
                    agents.append("claude")
                    if p.get("claude_session_id"):
                        sids.append("c:" + p["claude_session_id"][:8])
                if p.get("codex_running"):
                    agents.append("codex")
                    if p.get("codex_session_id"):
                        sids.append("x:" + p["codex_session_id"][:8])
                cwd = (p.get("cwd") or "").rstrip("/")
                if cwd:
                    projects.add(os.path.basename(cwd) or cwd)
            wins.append({
                "index": w.get("index"),
                "name": w.get("name", ""),
                "agents": agents,
                "projects": sorted(projects),
                "sids": sids,
            })
            shape.append((s.get("name"), w.get("name"), tuple(agents), tuple(sorted(projects))))
        sessions.append({
            "name": s.get("name"),
            "attached": s.get("attached", False),
            "windows": wins,
        })
    import hashlib
    digest = hashlib.md5(repr(shape).encode()).hexdigest()[:8]
    return {"sessions": sessions, "digest": digest}


def _render_summary(summ: dict, indent: str = "    ") -> str:
    lines = []
    for s in summ["sessions"]:
        tag = "*" if s["attached"] else " "
        lines.append(f"{indent}{tag} {s['name']}")
        for w in s["windows"]:
            parts = [f"win {w['index']} {w['name']}"]
            if w["agents"]:
                parts.append("[" + "+".join(w["agents"]) + "]")
            if w["projects"]:
                parts.append("@ " + ",".join(w["projects"]))
            if w["sids"]:
                parts.append("(" + " ".join(w["sids"]) + ")")
            lines.append(f"{indent}    " + " ".join(parts))
    return "\n".join(lines)


def cmd_pick(args: argparse.Namespace) -> int:
    """Rich snapshot listing. Collapses adjacent identical structures into runs."""
    if not SNAPSHOT_DIR.exists():
        print("no snapshots")
        return 0
    files = sorted(SNAPSHOT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    files = [p for p in files if p.name != "latest.json"]

    since_ts = until_ts = None
    if args.since:
        since_ts = dt.datetime.fromisoformat(args.since).timestamp()
    if args.until:
        until_ts = dt.datetime.fromisoformat(args.until).timestamp()
    if since_ts is not None:
        files = [p for p in files if p.stat().st_mtime >= since_ts]
    if until_ts is not None:
        files = [p for p in files if p.stat().st_mtime <= until_ts]

    if not files:
        print("no snapshots in range")
        return 0

    runs: list[dict] = []  # {digest, first, last, count, summary}
    for p in files:
        summ = _summarize_snapshot(p)
        if summ is None:
            continue
        mt = dt.datetime.fromtimestamp(p.stat().st_mtime)
        if args.all or not runs or runs[-1]["digest"] != summ["digest"]:
            runs.append({
                "digest": summ["digest"],
                "first_path": p, "last_path": p,
                "first_mt": mt, "last_mt": mt,
                "count": 1, "summary": summ,
            })
        else:
            runs[-1]["last_path"] = p
            runs[-1]["last_mt"] = mt
            runs[-1]["count"] += 1

    if args.limit:
        runs = runs[-args.limit:]

    for r in runs:
        span = (
            r["first_mt"].strftime("%Y-%m-%d %H:%M")
            if r["count"] == 1
            else f"{r['first_mt'].strftime('%Y-%m-%d %H:%M')} → {r['last_mt'].strftime('%H:%M')} ({r['count']}×)"
        )
        # Suggest the LAST snapshot of a run — usually the freshest state.
        pick = r["last_path"].name
        print(f"[{r['digest']}] {span}  pick: {pick}")
        print(_render_summary(r["summary"]))
        print()
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        p = resolve_snapshot(args.snapshot)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 8
    with open(p) as f:
        print(f.read())
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    try:
        a = resolve_snapshot(args.a)
        b = resolve_snapshot(args.b)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 8
    print(f"--- {a}\n+++ {b}\n")
    da = json.load(open(a))
    db = json.load(open(b))

    def panes_map(d):
        out = {}
        for s in d.get("tmux_sessions", []):
            for w in s["windows"]:
                for p in w["panes"]:
                    key = (s["name"], w["name"], p["index"])
                    out[key] = (
                        p.get("claude_session_id"),
                        p.get("codex_session_id"),
                        p.get("command"),
                    )
        return out

    ma, mb = panes_map(da), panes_map(db)
    for k in sorted(set(ma) | set(mb)):
        va, vb = ma.get(k), mb.get(k)
        if va != vb:
            print(f"{k}: {va} -> {vb}")
    return 0


# ───────────────────────── main ─────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(prog="tmux-restore")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot", help="capture current tmux + agent sessions")
    sp.add_argument("-q", "--quiet", action="store_true")
    sp.set_defaults(func=cmd_snapshot)

    rp = sub.add_parser("restore", help="replay a snapshot")
    rp.add_argument("--snapshot", help="path or basename; defaults to latest")
    rp.add_argument("--target-session", help="rename target session (single-session snapshots)")
    rp.add_argument("--only-sessions", help="comma-separated tmux session names to restore")
    rp.add_argument("--replace", action="store_true", help="kill existing target session first")
    rp.add_argument("--dry-run", action="store_true")
    rp.add_argument("--force", action="store_true", help="ignore staleness check")
    rp.add_argument("--force-host", action="store_true", help="ignore hostname mismatch")
    rp.add_argument("--no-verify", action="store_true", help="skip post-restore verification")
    rp.set_defaults(func=cmd_restore)

    vp = sub.add_parser("verify", help="compare current tmux state against a snapshot")
    vp.add_argument("--snapshot", help="path or basename; defaults to latest")
    vp.add_argument("--target-session")
    vp.add_argument("--only-sessions")
    vp.set_defaults(func=cmd_verify)

    lp = sub.add_parser("list", help="list snapshots")
    lp.set_defaults(func=cmd_list)

    pp = sub.add_parser("pick", help="rich snapshot list grouped by structural shape")
    pp.add_argument("--since", help="YYYY-MM-DD[THH:MM]")
    pp.add_argument("--until", help="YYYY-MM-DD[THH:MM]")
    pp.add_argument("--limit", type=int, default=50, help="show last N runs (0=all)")
    pp.add_argument("--all", action="store_true", help="don't collapse identical adjacent snapshots")
    pp.set_defaults(func=cmd_pick)

    shp = sub.add_parser("show", help="print snapshot JSON")
    shp.add_argument("snapshot", nargs="?")
    shp.set_defaults(func=cmd_show)

    dp = sub.add_parser("diff", help="diff two snapshots")
    dp.add_argument("a")
    dp.add_argument("b")
    dp.set_defaults(func=cmd_diff)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

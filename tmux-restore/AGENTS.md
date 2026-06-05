# tmux-restore: Reliable Session ID Capture

## Problem

`detect_agent_session()` in `tmux_restore.py` only captures claude/codex session
IDs when `--resume <UUID>` is in the process argv. Fresh-launched sessions
(`claude` with no flags) get `claude_running=True` but `claude_session_id=null`.
On restore, these panes launch a bare `claude` with no session context — the user
loses their conversation.

The old mtime-based fallback (`newest_jsonl_for_cwd`) was removed because
multiple panes sharing the same cwd all get mis-labelled with whatever JSONL was
modified most recently. That fix was correct; the approach below replaces it
without reintroducing the collision.

## Root Cause (Verified)

- `lsof` against claude PIDs: no JSONL or `/tmp/claude-*` files are held open.
  Claude opens, writes, and closes atomically.
- `CLAUDE_CODE_SESSION_ID` env var: exists in the process env, but tmux's global
  environment holds a single stale value that all panes inherit. Reading `ps -E`
  returns the same SID for every claude process — useless.
- No PID file, lock file, or inode-based mapping exists.

## Solution: SessionStart Hook + PID Mapping File

Claude Code's `SessionStart` hook receives JSON on stdin containing:

```json
{
  "session_id": "c1ff282f-9b30-4b66-8d9e-72e18688938e",
  "transcript_path": "/Users/karsinkk/.claude/projects/-Users-karsinkk/c1ff282f-...jsonl",
  "cwd": "/Users/karsinkk",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
```

This was empirically verified on 2026-05-23 with a test hook — `session_id` is
present for both fresh and resumed sessions.

### Architecture

```
SessionStart hook (shell script)
  ├── reads stdin JSON → extracts session_id
  ├── gets $PPID (claude is the parent process)
  ├── writes one line: PID:SID to mapping file
  └── uses flock for atomicity (multiple panes may start simultaneously)

detect_agent_session() (snapshot time)
  ├── current: argv regex for --resume UUID → works, keep it
  ├── NEW fallback: if claude_running but no SID in argv:
  │     read mapping file, look up claude PID → get SID
  └── prune dead PIDs from mapping file on each snapshot
```

## Implementation Plan

### Phase 1: Hook + Mapping File

**File: `~/.claude/hooks/tmux-restore-sid.sh`**

```bash
#!/bin/bash
# SessionStart hook: write PID→SID mapping for tmux-restore
MAPPING="$HOME/.local/share/tmux-restore/pid-sid.map"
mkdir -p "$(dirname "$MAPPING")"

# Read session_id from stdin JSON
SID=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
[ -z "$SID" ] && exit 0

# $PPID is the claude process that spawned this hook
PID=$PPID

# Atomic append with flock
(
  flock -x 200
  echo "$PID:$SID" >> "$MAPPING"
) 200>"$MAPPING.lock"
```

**Register in `~/.claude/settings.json`** — add to the `SessionStart` array:

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "bash \"$HOME/.claude/hooks/tmux-restore-sid.sh\""
    }
  ]
}
```

Note: `$HOME` does not expand in JSON. Use the literal path
`/Users/karsinkk/.claude/hooks/tmux-restore-sid.sh`.

### Phase 2: Modify `detect_agent_session()` in `tmux_restore.py`

**Add a new function** `read_pid_sid_map()`:

```python
PID_SID_MAP = STATE_DIR / "pid-sid.map"

def read_pid_sid_map() -> dict[int, str]:
    """Read the PID→SID mapping file written by the SessionStart hook."""
    mapping: dict[int, str] = {}
    if not PID_SID_MAP.exists():
        return mapping
    try:
        with open(PID_SID_MAP) as f:
            for line in f:
                line = line.strip()
                if ":" not in line:
                    continue
                pid_s, sid = line.split(":", 1)
                try:
                    mapping[int(pid_s)] = sid
                except ValueError:
                    continue
    except OSError:
        pass
    return mapping
```

**Modify `detect_agent_session()`** — after the existing argv-based detection,
add a fallback that checks the mapping file:

```python
def detect_agent_session(pane_pid: int, pane_cwd: str) -> dict[str, Any]:
    # ... existing code through the for-loop over descendant_pids ...
    
    # NEW: fallback for fresh sessions without --resume in argv
    if result["claude_running"] and not result["claude_session_id"]:
        pid_map = read_pid_sid_map()
        for pid in descendant_pids(pane_pid):
            if pid in pid_map:
                sid = pid_map[pid]
                # Verify the JSONL exists
                path = HOME / ".claude" / "projects" / encoded_cwd(pane_cwd) / f"{sid}.jsonl"
                if not path.exists():
                    for proj in (HOME / ".claude" / "projects").glob("*"):
                        candidate = proj / f"{sid}.jsonl"
                        if candidate.exists():
                            path = candidate
                            break
                    else:
                        path = None
                result["claude_session_id"] = sid
                result["claude_args"] = f"(from hook map, pid={pid})"
                if path and path.exists():
                    result["claude_session_path"] = str(path)
                    try:
                        result["claude_session_mtime"] = dt.datetime.fromtimestamp(
                            path.stat().st_mtime
                        ).astimezone().isoformat(timespec="seconds")
                    except OSError:
                        pass
                break
    
    return result
```

### Phase 3: Mapping File Cleanup

**In `cmd_snapshot()`**, after writing the snapshot, prune dead PIDs:

```python
def prune_pid_sid_map() -> None:
    """Remove entries whose PID no longer exists."""
    if not PID_SID_MAP.exists():
        return
    live_lines = []
    with open(PID_SID_MAP) as f:
        for line in f:
            line = line.strip()
            if ":" not in line:
                continue
            pid_s, sid = line.split(":", 1)
            try:
                pid = int(pid_s)
                os.kill(pid, 0)  # check if process exists
                live_lines.append(f"{pid}:{sid}")
            except (ValueError, ProcessLookupError, PermissionError):
                continue
    try:
        with open(PID_SID_MAP, "w") as f:
            f.write("\n".join(live_lines) + "\n" if live_lines else "")
    except OSError:
        pass
```

Call from `cmd_snapshot()` right after `prune_snapshots()`.

### Phase 4: Codex Support

Codex does NOT have a hook system. Two options:

**Option A (preferred): Shell wrapper at `~/.local/bin/codex-wrapper`**

Only needed if codex is used. Create a wrapper that logs PID→SID before exec:

```bash
#!/bin/bash
MAPPING="$HOME/.local/share/tmux-restore/pid-sid-codex.map"
mkdir -p "$(dirname "$MAPPING")"

# If "resume <UUID>" is in args, the existing argv detection works — skip
if echo "$@" | grep -qE 'resume\s+[0-9a-f-]{36}'; then
  exec /usr/local/bin/codex "$@"
fi

# For fresh launches, generate a session ID and log it
# (codex doesn't support --session-id, so we can only log post-hoc)
exec /usr/local/bin/codex "$@"
```

Since codex doesn't expose its SID externally and has no hook system, the
wrapper approach is limited. Check if codex keeps rollout files open via
`lsof -p <codex_pid>` — if it does, the SID is in the path and
`detect_agent_session()` can extract it directly (add lsof-based detection).

If codex doesn't keep files open either, the pragmatic answer is: codex's
existing `resume <UUID>` argv detection is the only reliable method. Document
this limitation.

**Option B: lsof fallback in `detect_agent_session()`**

For codex specifically, try `lsof -p <pid>` looking for `rollout-*.jsonl` paths.
Only attempt this if the argv regex fails:

```python
if result["codex_running"] and not result["codex_session_id"]:
    for pid in descendant_pids(pane_pid):
        if not is_codex_process(proc_name(pid), proc_args(pid)):
            continue
        rc, out, _ = run_status(["lsof", "-p", str(pid)])
        if rc != 0:
            continue
        for line in out.splitlines():
            m = re.search(r"rollout-.*?-(" + UUID_RE.pattern + r")\.jsonl", line)
            if m:
                result["codex_session_id"] = m.group(1)
                # ... resolve path, mtime ...
                break
```

Test whether this works by running `lsof -p <codex_pid>` while codex is active.
If codex doesn't hold rollout files open, skip this and document the limitation.

### Phase 5: Verification Fix

The `verify_restoration()` function (line 784) has a race condition: it checks
for claude descendant processes with the expected SID in their argv, but
hook-mapped sessions won't have the SID in argv. The verification should also
accept hook-mapped sessions as valid:

```python
# In verify_restoration(), after the current descendant check:
if not found:
    # Check hook mapping — SID may not be in argv for fresh sessions
    pid_map = read_pid_sid_map()
    for child in descendant_pids(pane_pid):
        if child in pid_map and pid_map[child] == expected_sid:
            found = True
            break
```

### Phase 6: Tests

Add tests to `test_tmux_restore.py`:

1. **test_pid_sid_map_read** — write a mapping file, verify `read_pid_sid_map()`
   parses it correctly.
2. **test_pid_sid_map_prune** — write entries with dead PIDs, verify pruning
   removes them.
3. **test_detect_agent_session_hook_fallback** — mock a claude process without
   `--resume` in argv, write a mapping entry, verify `detect_agent_session()`
   picks up the SID.
4. **test_mapping_file_missing** — verify graceful handling when the mapping file
   doesn't exist.
5. **test_concurrent_hook_writes** — verify flock prevents corruption under
   parallel appends.

## File Inventory

| File | Action |
|---|---|
| `~/.claude/hooks/tmux-restore-sid.sh` | CREATE — SessionStart hook script |
| `~/.claude/settings.json` | EDIT — add hook to SessionStart array |
| `tmux_restore.py` lines 213-280 | EDIT — add hook-map fallback to `detect_agent_session()` |
| `tmux_restore.py` near line 407 | EDIT — add `prune_pid_sid_map()` call |
| `tmux_restore.py` lines 784-844 | EDIT — update `verify_restoration()` for hook-mapped SIDs |
| `test_tmux_restore.py` | EDIT — add tests for mapping file read/write/prune |
| `install.sh` | EDIT — create hook script and register in settings.json |

## Constraints

- Do NOT reintroduce mtime-based JSONL guessing. The cross-pane collision bug it
  causes is worse than missing SIDs.
- Do NOT modify the snapshot schema version. The new `claude_args` value
  `"(from hook map, pid=NNNN)"` is informational; the schema fields are
  unchanged.
- The hook must be fast (< 1 second). The current implementation is a single
  `python3 -c` call + file append. If python3 startup is too slow, rewrite in
  pure bash using `sed`/`awk` to parse JSON.
- Pre-existing sessions (running before the hook is installed) will continue to
  get `claude_running=True` with no SID. This is acceptable — the hook only
  captures sessions started after installation.

## Fallback: Wrapper Approach

If the hook approach proves unreliable (e.g., hooks disabled via `--bare`,
hooks not firing for some session types), a `~/bin/claude` wrapper is the
alternative:

```bash
#!/bin/bash
REAL=$(command -v claude)
SID=$(uuidgen | tr '[:upper:]' '[:lower:]')
MAPPING="$HOME/.local/share/tmux-restore/pid-sid.map"
mkdir -p "$(dirname "$MAPPING")"
echo "$$:$SID" >> "$MAPPING"
exec "$REAL" --session-id "$SID" "$@"
```

This forces every session to have a SID in argv, making the existing argv
regex work. Downside: bypasses claude's own SID generation, which may break
`--continue` pickers. Test before deploying.

## Verification

After implementation, run this end-to-end test:

1. `tmux-restore snapshot` — check `claude_session_id` is non-null for all
   claude panes (both fresh and resumed).
2. `tmux-restore restore --dry-run` — verify all claude panes get
   `claude --resume <uuid>` in the dry-run output.
3. Kill the tmux session, restore, and verify each pane resumes the correct
   conversation.

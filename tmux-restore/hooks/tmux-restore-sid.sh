#!/usr/bin/env bash
# Claude SessionStart hook: map the live Claude PID to the session UUID.
set -euo pipefail

MAPPING="$HOME/.local/share/tmux-restore/pid-sid.map"
mkdir -p "$(dirname "$MAPPING")"

TMUX_RESTORE_HOOK_PARENT="$PPID" python3 -c '
import fcntl
import json
import os
import re
import subprocess
import sys

mapping = sys.argv[1]
uuid_re = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

sid = str(payload.get("session_id") or "")
if not uuid_re.fullmatch(sid):
    sys.exit(0)


def ps_field(pid, field):
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", f"{field}="],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        ).stdout.strip()
    except Exception:
        return ""
    return out


def is_claude_process(pid):
    name = ps_field(pid, "comm")
    args = ps_field(pid, "args")
    return name == "claude" or (name == "node" and ("claude" in args or "/.claude/" in args))


try:
    pid = int(os.environ.get("TMUX_RESTORE_HOOK_PARENT", ""))
except ValueError:
    sys.exit(0)

fallback_pid = pid
found_claude = False
for _ in range(4):
    if is_claude_process(pid):
        found_claude = True
        break
    parent = ps_field(pid, "ppid")
    try:
        pid = int(parent)
    except ValueError:
        break
if not found_claude:
    pid = fallback_pid

lock_path = mapping + ".lock"
os.makedirs(os.path.dirname(mapping), exist_ok=True)
with open(lock_path, "a") as lockf:
    fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
    with open(mapping, "a") as f:
        f.write(f"{pid}:{sid}\n")
' "$MAPPING" || true

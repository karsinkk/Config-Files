#!/usr/bin/env bash
# Auto-restore tmux sessions after crash/reboot.
# Runs via launchd at login. Only restores when:
#   1. A valid snapshot exists (< 24h old)
#   2. No tmux sessions are currently running
#   3. The snapshot has at least one session with agent panes
set -euo pipefail

RESTORE="$HOME/.local/bin/tmux-restore"
LOG="$HOME/.local/share/tmux-restore/restore-on-login.log"
SNAPSHOT_DIR="$HOME/.local/share/tmux-restore/snapshots"
LATEST="$SNAPSHOT_DIR/latest.json"

log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*" >> "$LOG"; }

if [ ! -x "$RESTORE" ] && [ ! -f "$RESTORE" ]; then
    log "tmux-restore not found at $RESTORE"
    exit 0
fi

# Wait for terminal/tmux to be ready (login services can race)
sleep 5

# Check if tmux server is already running with sessions
if tmux list-sessions >/dev/null 2>&1; then
    count=$(tmux list-sessions 2>/dev/null | wc -l | tr -d ' ')
    if [ "$count" -gt 0 ]; then
        log "tmux already has $count sessions; skipping restore"
        exit 0
    fi
fi

# Check for a valid snapshot
if [ ! -L "$LATEST" ] && [ ! -f "$LATEST" ]; then
    log "no latest snapshot; skipping restore"
    exit 0
fi

# Resolve the actual snapshot file
if [ -L "$LATEST" ]; then
    SNAP_FILE="$SNAPSHOT_DIR/$(readlink "$LATEST")"
else
    SNAP_FILE="$LATEST"
fi

if [ ! -f "$SNAP_FILE" ]; then
    log "snapshot file $SNAP_FILE missing; skipping restore"
    exit 0
fi

# Check age: skip if > 24 hours old
AGE=$(( $(date +%s) - $(stat -f %m "$SNAP_FILE") ))
if [ "$AGE" -gt 86400 ]; then
    log "snapshot is ${AGE}s old (>24h); skipping restore"
    exit 0
fi

# Check if snapshot has agent panes worth restoring
HAS_AGENTS=$(python3 -c "
import json, sys
try:
    d = json.load(open('$SNAP_FILE'))
    agents = sum(1 for s in d.get('tmux_sessions',[]) for w in s['windows'] for p in w['panes']
                 if p.get('claude_session_id') or p.get('codex_session_id'))
    print(agents)
except Exception:
    print(0)
" 2>/dev/null)

if [ "$HAS_AGENTS" = "0" ]; then
    log "snapshot has no agent sessions; skipping restore"
    exit 0
fi

log "restoring from $SNAP_FILE ($HAS_AGENTS agent panes, ${AGE}s old)"
python3 "$RESTORE" restore --no-verify --force 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
log "restore exit code: $RC"
exit "$RC"

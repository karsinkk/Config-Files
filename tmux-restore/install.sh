#!/usr/bin/env bash
# Idempotent installer for tmux-restore. Re-running is safe.
set -euo pipefail

REPO="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BIN="$HOME/.local/bin/tmux-restore"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_NAME="com.karsinkk.tmux-restore.plist"
PLIST_DST="$LAUNCH_AGENTS/$PLIST_NAME"
LOGIN_PLIST_NAME="com.karsinkk.tmux-restore-on-login.plist"
LOGIN_PLIST_DST="$LAUNCH_AGENTS/$LOGIN_PLIST_NAME"
TMUX_CONF="$HOME/.tmux.conf"
CLAUDE_HOOK_SRC="$REPO/hooks/tmux-restore-sid.sh"
CLAUDE_HOOK_DST="$HOME/.claude/hooks/tmux-restore-sid.sh"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
HOOK_MARKER="# tmux-restore hooks (managed by install.sh — do not edit between markers)"
HOOK_END="# end tmux-restore hooks"

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/tmux-restore/snapshots" "$LAUNCH_AGENTS" "$HOME/.claude/hooks"

# 1. symlink the script
ln -sfn "$REPO/tmux_restore.py" "$BIN"
chmod +x "$REPO/tmux_restore.py"
echo "[install] symlinked $BIN -> $REPO/tmux_restore.py"

# 2. install launchd plist (template substitution: __HOME__ -> $HOME)
sed "s|__HOME__|$HOME|g" "$REPO/$PLIST_NAME" > "$PLIST_DST"
echo "[install] wrote $PLIST_DST"

# 2b. install restore-on-login plist
sed "s|__HOME__|$HOME|g" "$REPO/$LOGIN_PLIST_NAME" > "$LOGIN_PLIST_DST"
echo "[install] wrote $LOGIN_PLIST_DST"

# 3. load via launchctl bootstrap (unload first to refresh)
UID_=$(id -u)
launchctl bootout "gui/$UID_/com.karsinkk.tmux-restore" 2>/dev/null || true
launchctl bootstrap "gui/$UID_" "$PLIST_DST"
launchctl bootout "gui/$UID_/com.karsinkk.tmux-restore-on-login" 2>/dev/null || true
launchctl bootstrap "gui/$UID_" "$LOGIN_PLIST_DST"
echo "[install] launchctl bootstrap done (snapshot + restore-on-login)"

# 4. install Claude SessionStart hook idempotently
cp "$CLAUDE_HOOK_SRC" "$CLAUDE_HOOK_DST"
chmod +x "$CLAUDE_HOOK_DST"
python3 - "$CLAUDE_SETTINGS" "$CLAUDE_HOOK_DST" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_path = sys.argv[2]
command = f'bash "{hook_path}"'
entry = {"hooks": [{"type": "command", "command": command}]}

if settings_path.exists():
    try:
        data = json.loads(settings_path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid Claude settings JSON: {settings_path}: {e}") from e
else:
    data = {}

hooks = data.setdefault("hooks", {})
session_start = hooks.setdefault("SessionStart", [])
for existing in session_start:
    for hook in existing.get("hooks", []):
        if hook.get("command") == command:
            break
    else:
        continue
    break
else:
    session_start.append(entry)
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
PY
echo "[install] installed Claude SessionStart hook at $CLAUDE_HOOK_DST"

# 5. append tmux hooks idempotently
if [ -f "$TMUX_CONF" ] && grep -q "$HOOK_MARKER" "$TMUX_CONF"; then
    echo "[install] tmux hooks already present in $TMUX_CONF"
else
    cat >> "$TMUX_CONF" <<EOF

$HOOK_MARKER
set-hook -g window-linked   "run-shell -b '$BIN snapshot --quiet'"
set-hook -g window-unlinked "run-shell -b '$BIN snapshot --quiet'"
set-hook -g pane-died       "run-shell -b '$BIN snapshot --quiet'"
set-hook -g client-detached "run-shell -b '$BIN snapshot --quiet'"
$HOOK_END
EOF
    echo "[install] appended tmux hooks to $TMUX_CONF"
fi

# 6. reload tmux hooks if server is running
if tmux info >/dev/null 2>&1; then
    tmux source-file "$TMUX_CONF" 2>/dev/null || true
    echo "[install] reloaded tmux config"
fi

echo "[install] done. Run a snapshot now: tmux-restore snapshot"

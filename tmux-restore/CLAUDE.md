# tmux-restore

Deterministic tmux session snapshot and restore for claude/codex agent panes.

## What this project does

Captures per-pane state (cwd, running process, agent session ID) via `tmux_restore.py snapshot`, then restores panes with the correct `claude --resume <UUID>` or `codex resume <UUID>` commands. The goal is zero-conversation-loss reboots.

## Key files

- `tmux_restore.py` — main script: snapshot, restore, verify, prune
- `test_tmux_restore.py` — pytest suite
- `hooks/` — Claude Code SessionStart hook for PID→SID mapping
- `install.sh` — registers hooks and launchd agents
- `build_sites_index.py` — sites index builder (separate utility)

## Architecture

Session ID capture uses two mechanisms:
1. **argv regex** — detects `--resume <UUID>` in process args (works for resumed sessions)
2. **SessionStart hook** — writes PID→SID to `~/.local/share/tmux-restore/pid-sid.map` (works for fresh sessions)

Snapshots are JSON files in `~/.local/share/tmux-restore/snapshots/`.

## Constraints

- Never reintroduce mtime-based JSONL guessing. Cross-pane cwd collisions make it unreliable.
- Hook must complete in < 1 second. Pure bash or single `python3 -c` call.
- Do not modify the snapshot JSON schema without updating `test_tmux_restore.py`.
- Pre-existing sessions (started before hook install) will lack SIDs. This is acceptable.

## Verify

```bash
python3 -m pytest test_tmux_restore.py -v
python3 tmux_restore.py snapshot --dry-run
```

## Related

- AGENTS.md contains the full implementation plan for the hook-based SID capture
- Launchd agents: `com.karsinkk.tmux-restore.plist`, `com.karsinkk.sites-index.plist`

# karsin terminal setup

One script, `setup.sh`, reproduces karsinkk's tmux + zsh + iTerm2 environment on a
fresh Mac: tmux with a `Ctrl-a` prefix, TPM with 9 plugins, 10 switchable themes,
session persistence at two layers (tmux-resurrect/continuum plus a custom
snapshot/restore daemon for Claude/Codex agent panes), FiraCode Nerd Font, and an
iTerm2 profile carrying the font and color scheme. All configs are embedded in the
script as heredocs — no other files needed.

## Run it

```bash
bash setup.sh
```

Re-running is safe: every step is idempotent and existing files are backed up as
`<file>.bak.<timestamp>` before being touched.

Dry run (writes config files only — no Homebrew, no git clones, no daemons):

```bash
TERMSETUP_EXTRACT_ONLY=1 bash setup.sh
```

## What it changes — read before running

| Target | Change |
|---|---|
| `~/.config/tmux/` | tmux.conf + 10 themes + 3 status-bar scripts |
| `~/.tmux.conf` | symlink to `~/.config/tmux/tmux.conf` |
| `~/.config/tmux/plugins/` | TPM + 12 plugin/theme repos (4 pinned to exact commits) |
| `~/.zshrc` | appends one marker-guarded block (PATH, iTerm2 integration, tmux aliases) |
| `~/projects/tmux-restore/` | session snapshot/restore tool (Python, ~1,200 lines) |
| `~/Library/LaunchAgents/` | **two launchd agents**: `com.karsinkk.tmux-restore` (periodic snapshots) and `com.karsinkk.tmux-restore-on-login` (restore at login) |
| `~/.claude/settings.json` | **adds a SessionStart hook** that records Claude session IDs so tmux panes can be restored with `claude --resume <id>` |
| `~/Library/Application Support/iTerm2/DynamicProfiles/` | `karsin-shared.json` profile (font + colors only) |
| Homebrew | installs `tmux` and `font-fira-code-nerd-font` (offers to install brew itself if missing) |

The launchd agents and the Claude-settings edit come from the tmux-restore tool.
If you don't want a background daemon or any change to your Claude config:

```bash
TERMSETUP_SKIP_TMUX_RESTORE=1 bash setup.sh
```

You still get session persistence via tmux-resurrect/continuum; you lose only the
automatic `claude --resume` pane restoration after reboots.

## Verify after install

```bash
tmux -V                                  # expect tmux 3.x
ls ~/.config/tmux/plugins                # expect 13 directories (tpm + 12)
zsh -ic 'type t tnew ta tls tcc tcca'    # aliases defined
launchctl list | grep karsinkk           # 2 agents (unless skipped)
tmux-restore snapshot --dry-run          # snapshotter runs (unless skipped)
ls ~/Library/Fonts | grep -ci firacode   # > 0
```

Then in iTerm2: **Settings → Profiles → "Karsin Shared" → Other Actions → Set as
Default**, restart iTerm2, and run `t`.

## Daily use

| Key / command | Action |
|---|---|
| `t` | attach-or-create the `main` tmux session |
| `tcc` | same, in iTerm2 native-window (`-CC`) mode |
| `tnew <name>` / `ta` / `tls` | new named session / attach / list |
| `Ctrl-a` | tmux prefix |
| `prefix` `\|` / `-` | split pane horizontally / vertically |
| `Ctrl-arrows` or `Alt-arrows` | move between panes |
| `Shift-Left/Right` | previous / next window |
| `prefix` `T` | theme menu (dracula, catppuccin, tokyo night, kanagawa, …) |
| `prefix` `B` | status-bar style menu |
| `prefix` `E` | status-bar icon presets (nerd font / emoji / plain) |
| `prefix` `r` | reload tmux config |

## For the Claude running this

- The script is generated from live configs by `build_setup.py` (not needed to run it).
- Run the `TERMSETUP_EXTRACT_ONLY=1` pass first if you want to inspect what gets
  written before any install happens.
- If the user already has a `~/.tmux.conf` or tmux plugin setup, the backups land
  next to the originals; merge by hand rather than re-running with edits.
- The theme menu (`prefix+T`) assumes the four pinned theme repos cloned by the
  script; if a clone fails (network), only that theme's menu entry breaks — the
  default `dracula-local` theme is self-contained.
- Nerd Font glyphs in the status bar require the terminal font to be a FiraCode
  Nerd Font variant; the iTerm2 dynamic profile sets `FiraCodeNFM-SemBd 18`.

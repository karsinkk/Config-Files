# Config-Files

Live terminal environment for macOS: tmux (C-a prefix, TPM, switchable themes),
zsh aliases, iTerm2 integration, and session restore for Claude/Codex agent panes.
Refreshed 2026-06 from the working machine; the 2018-era dotfiles are replaced.

## Fastest path: the installer

[`karsin-terminal-setup/setup.sh`](karsin-terminal-setup/setup.sh) is a single
self-contained script that reproduces the whole environment on a fresh Mac —
every config below is embedded in it. See
[`karsin-terminal-setup/README.md`](karsin-terminal-setup/README.md) for what it
changes, opt-out flags, and verification steps.

```bash
bash karsin-terminal-setup/setup.sh
```

## Layout

| Path | What it is |
|---|---|
| `karsin-terminal-setup/` | standalone installer (`setup.sh`), its README, and the generator (`build_setup.py`) |
| `tmux/` | live tmux config: `tmux.conf` (installs to `~/.config/tmux/`), 10 themes, 3 status-bar scripts |
| `tmux-restore/` | tmux session snapshot/restore daemon — restores panes with `claude --resume <id>` after reboots; has its own `install.sh` and pytest suite |
| `.zshrc` | PATH, iTerm2 shell integration, tmux aliases (`t`, `ta`, `tls`, `tcc`, `tcca`) |
| `Brewfile` | `brew bundle dump` of installed packages (2026-06-04) |
| `hadoop/` | legacy Hadoop configs (unmaintained) |
| `.bashrc` | legacy bash config (shell is zsh now) |

Note: `tmux/tmux.conf` ends with machine-specific tmux-restore hooks pointing at
`~/.local/bin/tmux-restore`; `tmux-restore/install.sh` appends those for you, so
strip them if you take the conf without the daemon.

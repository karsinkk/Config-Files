#!/usr/bin/env python3
"""Generate setup.sh from the live configs on this machine.

Reads the real tmux/zsh/iTerm2/tmux-restore sources, embeds them as
quoted heredocs, and emits a single self-contained installer a friend
can run on a fresh Mac. Re-run this whenever the live configs change.

Safety invariants enforced at build time:
  - no heredoc delimiter collision with any embedded line
  - no '/Users/karsinkk' string anywhere in the generated script
  - iTerm2 profile is a key whitelist (colors/font only), never the raw plist
"""

import json
import plistlib
import re
import sys
import uuid
from pathlib import Path

HOME = Path.home()
OUT = Path(__file__).parent / "setup.sh"

TMUX_DIR = HOME / ".config/tmux"
RESTORE_DIR = HOME / "projects/tmux-restore"
ITERM_PLIST = HOME / "Library/Preferences/com.googlecode.iterm2.plist"

HOOK_MARKER = "# tmux-restore hooks (managed by install.sh — do not edit between markers)"
HOOK_END = "# end tmux-restore hooks"

# Pinned commits captured from the working install on 2026-06-04.
# Repos were renamed upstream (tokyo-night -> powerkit, kanagawa -> ukiyo);
# local directory names must match the paths the theme files source.
THEME_REPOS = [
    ("https://github.com/catppuccin/tmux.git", "catppuccin",
     "d2d25bd3393fe43f19eb4fff6cdd2bdf5578e622"),  # tag v2.3.0
    ("https://github.com/dracula/tmux.git", "dracula",
     "a0830546479f4cc2e865099749a67914ae74a0f1"),
    ("https://github.com/Nybkox/tmux-ukiyo.git", "tmux-kanagawa",
     "dd8730a2a41da79425c11c0cea69e0bd81545e19"),
    ("https://github.com/fabioluciano/tmux-powerkit.git", "tmux-tokyo-night",
     "139be6bbd57dbedfc6c534e72a440147ad0ab4d4"),
]

ZSHRC_BLOCK = """\
# >>> karsin terminal setup >>>
export PATH="$HOME/.local/bin:$PATH"

# tmux + iTerm2 integration
export ITERM_ENABLE_SHELL_INTEGRATION_WITH_TMUX=1
if [ -e "$HOME/.iterm2_shell_integration.zsh" ]; then
  source "$HOME/.iterm2_shell_integration.zsh"
fi

alias t='tmux new-session -A -s main'
tnew() {
  if [ $# -eq 0 ]; then
    tmux new-session
  else
    local session_name="$1"
    shift
    tmux new-session -s "$session_name" "$@"
  fi
}
alias ta='tmux attach-session'
tls() {
  tmux list-sessions 2>/dev/null || true
}
alias tcc='tmux -CC new-session -A -s main'
alias tcca='tmux -CC attach-session'
# <<< karsin terminal setup <<<"""

ITERM_PROFILE_KEYS = re.compile(
    r"^("
    r"Ansi \d+ Color( \((Light|Dark)\))?"
    r"|(Foreground|Background|Bold|Cursor|Cursor Text|Cursor Guide|Selection"
    r"|Selected Text|Badge|Link) Color( \((Light|Dark)\))?"
    r"|Use Separate Colors for Light and Dark Mode"
    r"|Normal Font|Non Ascii Font|Use Non-ASCII Font"
    r"|ASCII Ligatures|ASCII Anti Aliased|Non-ASCII Anti Aliased"
    r"|Use Bold Font|Use Bright Bold|Use Italic Font"
    r"|Blinking Cursor|Scrollback Lines|Unlimited Scrollback"
    r"|Terminal Type|Horizontal Spacing|Vertical Spacing"
    r"|Silence Bell|Visual Bell|Flashing Bell"
    r"|Mouse Reporting|Transparency|Blur"
    r"|Character Encoding|Ambiguous Double Width"
    r")$"
)


def tmux_conf_without_hooks() -> str:
    """Live tmux.conf minus the tmux-restore hook block.

    tmux-restore/install.sh re-appends the block with the friend's $HOME,
    so stripping it here is what makes the paths portable.
    """
    lines = (TMUX_DIR / "tmux.conf").read_text().splitlines()
    start = lines.index(HOOK_MARKER)
    end = lines.index(HOOK_END)
    # also drop the blank separator line preceding the marker
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1
    kept = lines[:start] + lines[end + 1:]
    return "\n".join(kept).rstrip("\n") + "\n"


def iterm_profile_json() -> str:
    with open(ITERM_PLIST, "rb") as f:
        plist = plistlib.load(f)
    bookmarks = plist["New Bookmarks"]
    src = bookmarks[0]
    prof = {k: v for k, v in src.items() if ITERM_PROFILE_KEYS.match(k)}
    missing = [k for k in ("Normal Font", "Foreground Color", "Background Color")
               if k not in prof]
    if missing:
        sys.exit(f"iTerm2 profile extract missing required keys: {missing}")
    for k, v in prof.items():
        if isinstance(v, bytes):
            sys.exit(f"iTerm2 profile key {k!r} is binary data; refusing to embed")
    prof["Name"] = "Karsin Shared"
    prof["Guid"] = str(uuid.uuid4()).upper()
    return json.dumps({"Profiles": [prof]}, indent=2, sort_keys=True) + "\n"


class Emitter:
    def __init__(self):
        self.parts = []
        self.n = 0

    def raw(self, text: str):
        self.parts.append(text)

    def heredoc_write(self, dest: str, content: str, mode=None):
        """Emit: cat > dest <<'DELIM' ... DELIM  (quoted: no expansion)."""
        self.n += 1
        delim = f"EOF_KTS_{self.n}"
        if any(line == delim for line in content.splitlines()):
            sys.exit(f"heredoc delimiter collision for {dest}")
        if not content.endswith("\n"):
            content += "\n"
        self.parts.append(f'cat > "{dest}" <<\'{delim}\'\n{content}{delim}\n')
        if mode:
            self.parts.append(f'chmod {mode} "{dest}"\n')
        self.parts.append("\n")


def build() -> str:
    e = Emitter()
    e.raw(f"""#!/usr/bin/env bash
# karsin terminal setup — tmux + zsh + iTerm2 environment
#
# Generated by build_setup.py from karsinkk's live configs (2026-06-04).
# What it installs:
#   - tmux (Homebrew) with a C-a prefix config, TPM + 9 plugins,
#     10 switchable themes (prefix+T), status-bar styles (prefix+B)
#   - tmux-restore: session snapshot/restore for claude/codex agent panes
#     (launchd agents + a Claude Code SessionStart hook — see README)
#   - zsh aliases: t / ta / tls / tcc / tcca + iTerm2 shell integration
#   - FiraCode Nerd Font + an iTerm2 dynamic profile (font + colors only)
#
# Flags (env vars):
#   TERMSETUP_EXTRACT_ONLY=1      write embedded files and exit
#                                 (no brew/git/launchctl/network)
#   TERMSETUP_SKIP_TMUX_RESTORE=1 skip the tmux-restore daemon + Claude hook
#
# Idempotent: re-running is safe. Existing files are backed up as *.bak.<ts>.
set -euo pipefail

EXTRACT_ONLY="${{TERMSETUP_EXTRACT_ONLY:-0}}"
SKIP_TMUX_RESTORE="${{TERMSETUP_SKIP_TMUX_RESTORE:-0}}"

say()  {{ printf '\\033[1;34m[setup]\\033[0m %s\\n' "$*"; }}
warn() {{ printf '\\033[1;33m[setup:warn]\\033[0m %s\\n' "$*"; }}

if [ "$(uname -s)" != "Darwin" ]; then
  warn "this script targets macOS (iTerm2, launchd, Homebrew casks)"
  [ "$EXTRACT_ONLY" = "1" ] || exit 1
fi

backup() {{
  if [ -e "$1" ] && [ ! -L "$1" ]; then
    cp -p "$1" "$1.bak.$(date +%s)"
    say "backed up $1"
  fi
}}

# ---------------------------------------------------------------------------
# Phase A: write all embedded files (pure file writes, no network)
# ---------------------------------------------------------------------------
say "writing config files"
mkdir -p "$HOME/.config/tmux/themes" "$HOME/.config/tmux/scripts" \\
         "$HOME/projects/tmux-restore/hooks" \\
         "$HOME/Library/Application Support/iTerm2/DynamicProfiles" \\
         "$HOME/.local/bin"

backup "$HOME/.config/tmux/tmux.conf"
""")

    # tmux.conf (hook block stripped; tmux-restore/install.sh re-adds it)
    e.heredoc_write("$HOME/.config/tmux/tmux.conf", tmux_conf_without_hooks())

    # themes + scripts, verbatim
    for f in sorted((TMUX_DIR / "themes").glob("*.tmux")):
        e.heredoc_write(f"$HOME/.config/tmux/themes/{f.name}", f.read_text())
    for f in sorted((TMUX_DIR / "scripts").glob("*.sh")):
        e.heredoc_write(f"$HOME/.config/tmux/scripts/{f.name}", f.read_text(), mode="+x")

    # tmux-restore project (working-tree versions)
    restore_files = [
        ("tmux_restore.py", "+x"),
        ("install.sh", "+x"),
        ("restore-on-login.sh", "+x"),
        ("com.karsinkk.tmux-restore.plist", None),
        ("com.karsinkk.tmux-restore-on-login.plist", None),
        ("hooks/tmux-restore-sid.sh", "+x"),
    ]
    for rel, mode in restore_files:
        e.heredoc_write(f"$HOME/projects/tmux-restore/{rel}",
                        (RESTORE_DIR / rel).read_text(), mode=mode)

    # iTerm2 dynamic profile (whitelisted font + color keys only)
    e.heredoc_write(
        "$HOME/Library/Application Support/iTerm2/DynamicProfiles/karsin-shared.json",
        iterm_profile_json())

    # ~/.tmux.conf symlink + zshrc block
    e.raw("""backup "$HOME/.tmux.conf"
ln -sfn "$HOME/.config/tmux/tmux.conf" "$HOME/.tmux.conf"
say "symlinked ~/.tmux.conf -> ~/.config/tmux/tmux.conf"

if [ -f "$HOME/.zshrc" ] && grep -qF '# >>> karsin terminal setup >>>' "$HOME/.zshrc"; then
  say "zshrc block already present"
else
  backup "$HOME/.zshrc"
""")
    e.n += 1
    delim = f"EOF_KTS_{e.n}"
    e.raw(f"  cat >> \"$HOME/.zshrc\" <<'{delim}'\n\n{ZSHRC_BLOCK}\n{delim}\n")
    e.raw("""  say "appended tmux/iTerm2 block to ~/.zshrc"
fi

if [ "$EXTRACT_ONLY" = "1" ]; then
  say "TERMSETUP_EXTRACT_ONLY=1 — files written, skipping installs"
  exit 0
fi

# ---------------------------------------------------------------------------
# Phase B: installs (Homebrew, git clones, launchd, shell integration)
# ---------------------------------------------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  say "Homebrew not found"
  read -r -p "Install Homebrew now? [y/N] " reply
  if [ "${reply:-n}" = "y" ] || [ "${reply:-n}" = "Y" ]; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
  else
    warn "skipping Homebrew; tmux and the Nerd Font will not be installed"
  fi
fi

if command -v brew >/dev/null 2>&1; then
  brew list tmux >/dev/null 2>&1 || brew install tmux
  brew list --cask font-fira-code-nerd-font >/dev/null 2>&1 \\
    || brew install --cask font-fira-code-nerd-font
  say "tmux $(tmux -V | cut -d' ' -f2) + FiraCode Nerd Font installed"
fi

clone_pin() {  # url dir commit
  local url="$1" dir="$HOME/.config/tmux/plugins/$2" commit="$3"
  if [ -d "$dir/.git" ]; then
    say "plugin $2 already cloned"
    return 0
  fi
  git clone --quiet "$url" "$dir"
  git -C "$dir" checkout --quiet "$commit" 2>/dev/null \\
    || warn "could not pin $2 to $commit; using default branch"
  say "cloned $2 @ ${commit:0:7}"
}

mkdir -p "$HOME/.config/tmux/plugins"
if [ ! -d "$HOME/.config/tmux/plugins/tpm/.git" ]; then
  git clone --quiet https://github.com/tmux-plugins/tpm \\
    "$HOME/.config/tmux/plugins/tpm"
  say "cloned tpm"
fi
""")
    for url, dirname, commit in THEME_REPOS:
        e.raw(f'clone_pin "{url}" "{dirname}" "{commit}"\n')
    e.raw("""
# Install the remaining TPM plugins (needs a tmux server with the conf loaded)
if command -v tmux >/dev/null 2>&1; then
  tmux start-server 2>/dev/null || true
  tmux new-session -d -s __karsin_setup 2>/dev/null || true
  "$HOME/.config/tmux/plugins/tpm/bin/install_plugins" \\
    || warn "tpm install_plugins failed; run prefix+I inside tmux instead"
  tmux kill-session -t __karsin_setup 2>/dev/null || true
fi

# tmux-restore: launchd agents + Claude Code SessionStart hook + tmux hooks.
# NOTE: this edits ~/.claude/settings.json and registers two launchd agents
# labeled com.karsinkk.*. Set TERMSETUP_SKIP_TMUX_RESTORE=1 to opt out.
if [ "$SKIP_TMUX_RESTORE" = "1" ]; then
  say "skipping tmux-restore install (TERMSETUP_SKIP_TMUX_RESTORE=1)"
else
  bash "$HOME/projects/tmux-restore/install.sh"
fi

# iTerm2 zsh shell integration
if [ ! -e "$HOME/.iterm2_shell_integration.zsh" ]; then
  curl -fsSL https://iterm2.com/shell_integration/zsh \\
    -o "$HOME/.iterm2_shell_integration.zsh"
  say "installed iTerm2 shell integration"
fi

say "done. Next steps:"
say "  1. restart iTerm2, then Settings > Profiles > 'Karsin Shared' > Other Actions > Set as Default"
say "  2. open a new shell and run: t        (attaches/creates the 'main' tmux session)"
say "  3. inside tmux: prefix is Ctrl-a; try prefix+T (themes), prefix+B (bar styles)"
""")
    return "".join(e.parts)


def main():
    script = build()
    if "/Users/karsinkk" in script:
        for i, line in enumerate(script.splitlines(), 1):
            if "/Users/karsinkk" in line:
                print(f"  line {i}: {line}", file=sys.stderr)
        sys.exit("generated script leaks /Users/karsinkk paths")
    OUT.write_text(script)
    OUT.chmod(0o755)
    print(f"wrote {OUT} ({len(script)} bytes, {script.count(chr(10))} lines)")


if __name__ == "__main__":
    main()

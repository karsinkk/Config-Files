export PATH="$HOME/.local/bin:$PATH"

# >>> tmux + iTerm2 integration >>>
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
# <<< tmux + iTerm2 integration <<<

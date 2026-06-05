# PowerKit public theme framework with Tokyo Night styling.
# It requires Bash 4.2+. macOS /bin/bash is 3.2, so this is dependency-gated.

if-shell -b 'test -x /opt/homebrew/bin/bash' \
  'set -g @powerkit_theme "tokyo-night"; set -g @powerkit_theme_variant "night"; set -g @powerkit_plugins "datetime,battery,cpu,memory,hostname"; set -g @powerkit_separator_style "rounded"; set -g @powerkit_elements_spacing "both"; set -g @powerkit_status_interval "5"; set -g @powerkit_theme_selector_key ""; set -g @powerkit_show_options_key ""; set -g @powerkit_show_keybindings_key ""; set -g @powerkit_cache_clear_key ""; set -g @powerkit_log_viewer_key ""; run-shell "PATH=/opt/homebrew/bin:$PATH ~/.config/tmux/plugins/tmux-tokyo-night/tmux-powerkit.tmux"' \
  'display-message "PowerKit needs Bash 4.2+; using tokyo-local instead"; set -g @karsin_tmux_theme tokyo-local; source-file ~/.config/tmux/themes/tokyo-local.tmux'

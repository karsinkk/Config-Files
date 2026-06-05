# Official Dracula theme plugin.

set -g @dracula-plugins "cpu-usage battery time"
set -g @dracula-show-powerline true
set -g @dracula-show-flags true
set -g @dracula-refresh-rate 5
set -g @dracula-military-time true
set -g @dracula-day-month true
set -g @dracula-time-format "%d/%m %H:%M"
set -g @dracula-show-left-icon "#S"

run-shell ~/.config/tmux/plugins/dracula/dracula.tmux

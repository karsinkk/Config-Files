# Official Catppuccin tmux theme, Mocha flavor.

set -g @catppuccin_flavor "mocha"
set -g @catppuccin_window_status_style "rounded"

run ~/.config/tmux/plugins/catppuccin/catppuccin.tmux

set -g status-left ""
set -g status-right "#{E:@catppuccin_status_cpu}"
set -agF status-right "#{E:@catppuccin_status_battery}"
set -ag status-right " #[fg=#{@thm_crust},bg=#{@thm_mauve},bold] %d/%m %H:%M "

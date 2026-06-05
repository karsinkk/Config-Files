# Tokyo Night-inspired local theme. No plugin or newer Bash required.

set -g status-style "fg=#c0caf5,bg=#1a1b26,bold"
set -g status-left "#[fg=#1a1b26,bg=#7aa2f7,bold] 󰆍 #S #[fg=#7aa2f7,bg=#1a1b26,nobold] "
set -g status-right "#[fg=#1a1b26,bg=#bb9af7,bold] 󰍛 #{cpu_percentage} #[fg=#1a1b26,bg=#9ece6a,bold] #{battery_icon} #{battery_percentage} #[fg=#1a1b26,bg=#f7768e,bold] %d/%m %H:%M "

if -F '#{==:#{@karsin_tmux_bar_style},chips}' 'set -g status-left "#[fg=#c0caf5,bg=#1a1b26] #[fg=#1a1b26,bg=#7aa2f7,bold] #S #[fg=#c0caf5,bg=#1a1b26] "; set -g status-right "#[fg=#1a1b26,bg=#414868] CPU #{cpu_percentage} #[fg=#1a1b26,bg=#9ece6a] #{battery_icon} #{battery_percentage} #[fg=#1a1b26,bg=#f7768e] %H:%M "'
if -F '#{==:#{@karsin_tmux_bar_style},powerline}' 'set -g status-left "#[fg=#1a1b26,bg=#7aa2f7,bold] #S #[fg=#7aa2f7,bg=#414868]"; set -g status-right "#[fg=#bb9af7,bg=#1a1b26]#[fg=#1a1b26,bg=#bb9af7,bold] CPU #{cpu_percentage} #[fg=#9ece6a,bg=#bb9af7]#[fg=#1a1b26,bg=#9ece6a,bold] #{battery_icon} #{battery_percentage} #[fg=#f7768e,bg=#9ece6a]#[fg=#1a1b26,bg=#f7768e,bold] %d/%m %H:%M "'
if -F '#{==:#{@karsin_tmux_bar_style},plain}' 'set -g status-left "#[fg=#1a1b26,bg=#7aa2f7,bold] #S #[fg=#7aa2f7,bg=#1a1b26,nobold] "; set -g status-right "#[fg=#c0caf5,bg=#1a1b26,bold] CPU:#{cpu_percentage} | Batt: #{battery_icon} #{battery_percentage} #{battery_remain} #[fg=#1a1b26,bg=#f7768e,bold] %d/%m %H:%M "'
if -F '#{==:#{@karsin_tmux_bar_style},compact}' 'set -g status-left "#[fg=#1a1b26,bg=#7aa2f7,bold] #S "; set -g status-right "#[fg=#c0caf5,bg=#1a1b26,bold] #{cpu_percentage} #{battery_icon} #{battery_percentage} #[fg=#1a1b26,bg=#f7768e,bold] %H:%M "'
if -F '#{==:#{@karsin_tmux_bar_style},full}' 'set -g status-left "#[fg=#1a1b26,bg=#7aa2f7,bold] 󰆍 #S #[fg=#7aa2f7,bg=#414868]"; set -g status-right "#[fg=#7dcfff,bg=#1a1b26]#[fg=#1a1b26,bg=#7dcfff,bold] NET #{net_speed} #[fg=#bb9af7,bg=#7dcfff]#[fg=#1a1b26,bg=#bb9af7,bold] CPU #{cpu_percentage} #[fg=#9ece6a,bg=#bb9af7]#[fg=#1a1b26,bg=#9ece6a,bold] #{battery_icon} #{battery_percentage} #{battery_remain} #[fg=#f7768e,bg=#9ece6a]#[fg=#1a1b26,bg=#f7768e,bold] %a %d/%m %H:%M:%S "'

setw -g window-status-format "#[fg=#a9b1d6,bg=#24283b] #I:#W#F "
setw -g window-status-current-format "#[fg=#1a1b26,bg=#7aa2f7,bold] #I:#W#F "
setw -g window-status-style "fg=#a9b1d6,bg=#24283b"
setw -g window-status-current-style "fg=#1a1b26,bg=#7aa2f7,bold"
setw -g window-status-bell-style "fg=#1a1b26,bg=#f7768e,bold"

set -g window-style "fg=#414868,bg=default,dim"
set -g window-active-style "fg=#c0caf5,bg=default"
set -g pane-border-style "fg=#3b4261,bg=default"
set -g pane-active-border-style "fg=#7aa2f7,bg=default"
setw -g clock-mode-colour "#7aa2f7"
setw -g mode-style "fg=#1a1b26,bg=#7aa2f7,bold"
set -g message-style "fg=#1a1b26,bg=#e0af68,bold"
set -g message-command-style "fg=#1a1b26,bg=#7dcfff,bold"

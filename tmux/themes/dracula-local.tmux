# Dracula-inspired local theme. No plugin required.

set -g status-style "fg=#f8f8f2,bg=#282a36"

set -g status-left "#[fg=#bd93f9,bg=#282a36]#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_session} #S #[fg=#bd93f9,bg=#282a36] "
set -g status-right "#[fg=#a6e3a1,bg=#282a36]#[fg=#11111b,bg=#a6e3a1,bold] #{@karsin_tmux_icon_ram} #(~/.config/tmux/scripts/ram_percent.sh) #[fg=#a6e3a1,bg=#282a36] #[fg=#f9e2af,bg=#282a36]#[fg=#11111b,bg=#f9e2af,bold] #{@karsin_tmux_icon_cpu} #{cpu_percentage} #[fg=#f9e2af,bg=#282a36] #[fg=#ffb86c,bg=#282a36]#[fg=#11111b,bg=#ffb86c,bold] #{@karsin_tmux_icon_gpu} #(~/.config/tmux/scripts/gpu_percent.sh) #[fg=#ffb86c,bg=#282a36] #[fg=#cba6f7,bg=#282a36]#[fg=#11111b,bg=#cba6f7,bold] #{@karsin_tmux_icon_weather} #(~/.config/tmux/scripts/weather.sh #{@karsin_tmux_weather_location}) #{@karsin_tmux_icon_time} %H:%M #[fg=#cba6f7,bg=#282a36]"

if -F '#{==:#{@karsin_tmux_bar_style},online-rounded}' 'set -g status-left "#[fg=#bd93f9,bg=#282a36]#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_session} #S #[fg=#bd93f9,bg=#282a36] "; set -g status-right "#[fg=#a6e3a1,bg=#282a36]#[fg=#11111b,bg=#a6e3a1,bold] #{@karsin_tmux_icon_ram} #(~/.config/tmux/scripts/ram_percent.sh) #[fg=#a6e3a1,bg=#282a36] #[fg=#f9e2af,bg=#282a36]#[fg=#11111b,bg=#f9e2af,bold] #{@karsin_tmux_icon_cpu} #{cpu_percentage} #[fg=#f9e2af,bg=#282a36] #[fg=#ffb86c,bg=#282a36]#[fg=#11111b,bg=#ffb86c,bold] #{@karsin_tmux_icon_gpu} #(~/.config/tmux/scripts/gpu_percent.sh) #[fg=#ffb86c,bg=#282a36] #[fg=#cba6f7,bg=#282a36]#[fg=#11111b,bg=#cba6f7,bold] #{@karsin_tmux_icon_weather} #(~/.config/tmux/scripts/weather.sh #{@karsin_tmux_weather_location}) #{@karsin_tmux_icon_time} %H:%M #[fg=#cba6f7,bg=#282a36]"'
if -F '#{==:#{@karsin_tmux_bar_style},dracula-pro}' 'set -g status-left "#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_session} #S #[fg=#bd93f9,bg=#282a36,nobold]"; set -g status-right "#[fg=#6272a4,bg=#282a36]#[fg=#f8f8f2,bg=#6272a4] #{@karsin_tmux_icon_ram} #(~/.config/tmux/scripts/ram_percent.sh) #[fg=#44475a,bg=#6272a4]#[fg=#f8f8f2,bg=#44475a] #{@karsin_tmux_icon_cpu} #{cpu_percentage} #[fg=#ffb86c,bg=#44475a]#[fg=#282a36,bg=#ffb86c,bold] #{@karsin_tmux_icon_gpu} #(~/.config/tmux/scripts/gpu_percent.sh) #[fg=#bd93f9,bg=#ffb86c]#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_weather} #(~/.config/tmux/scripts/weather.sh #{@karsin_tmux_weather_location})  #{@karsin_tmux_icon_time} %H:%M "'
if -F '#{==:#{@karsin_tmux_bar_style},dracula-compact}' 'set -g status-left "#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_session} #S #[fg=#bd93f9,bg=#282a36]"; set -g status-right "#[fg=#44475a,bg=#282a36]#[fg=#f8f8f2,bg=#44475a] #{@karsin_tmux_icon_ram} #(~/.config/tmux/scripts/ram_percent.sh)  #{@karsin_tmux_icon_cpu} #{cpu_percentage}  #{@karsin_tmux_icon_gpu} #(~/.config/tmux/scripts/gpu_percent.sh)  #{@karsin_tmux_icon_weather} #(~/.config/tmux/scripts/weather.sh #{@karsin_tmux_weather_location}) #[fg=#bd93f9,bg=#44475a]#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_time} %H:%M "'
if -F '#{==:#{@karsin_tmux_bar_style},emoji-powerline}' 'set -g status-left "#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_session} #S #[fg=#bd93f9,bg=#44475a]"; set -g status-right "#[fg=#50fa7b,bg=#282a36]#[fg=#282a36,bg=#50fa7b,bold] #{@karsin_tmux_icon_ram} #(~/.config/tmux/scripts/ram_percent.sh) #[fg=#ffb86c,bg=#50fa7b]#[fg=#282a36,bg=#ffb86c,bold] #{@karsin_tmux_icon_cpu} #{cpu_percentage} #[fg=#ff79c6,bg=#ffb86c]#[fg=#282a36,bg=#ff79c6,bold] #{@karsin_tmux_icon_gpu} #(~/.config/tmux/scripts/gpu_percent.sh) #[fg=#bd93f9,bg=#ff79c6]#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_weather} #(~/.config/tmux/scripts/weather.sh #{@karsin_tmux_weather_location}) #{@karsin_tmux_icon_time} %H:%M "'
if -F '#{==:#{@karsin_tmux_bar_style},full}' 'set -g status-left "#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_session} #S #[fg=#bd93f9,bg=#282a36]"; set -g status-right "#[fg=#6272a4,bg=#282a36]#[fg=#f8f8f2,bg=#6272a4] #{@karsin_tmux_icon_ram} RAM #(~/.config/tmux/scripts/ram_percent.sh) #[fg=#44475a,bg=#6272a4]#[fg=#f8f8f2,bg=#44475a] #{@karsin_tmux_icon_cpu} CPU #{cpu_percentage} #[fg=#ffb86c,bg=#44475a]#[fg=#282a36,bg=#ffb86c,bold] #{@karsin_tmux_icon_gpu} GPU #(~/.config/tmux/scripts/gpu_percent.sh) #[fg=#bd93f9,bg=#ffb86c]#[fg=#282a36,bg=#bd93f9,bold] #{@karsin_tmux_icon_weather} #(~/.config/tmux/scripts/weather.sh #{@karsin_tmux_weather_location})  #{@karsin_tmux_icon_time} %a %d/%m %H:%M:%S "'
if -F '#{==:#{@karsin_tmux_bar_style},plain}' 'set -g status-left "#[fg=#bd93f9,bg=#282a36,bold] #{@karsin_tmux_icon_session} #S "; set -g status-right "#[fg=#f8f8f2,bg=#282a36] RAM #(~/.config/tmux/scripts/ram_percent.sh)  CPU #{cpu_percentage}  GPU #(~/.config/tmux/scripts/gpu_percent.sh)  WEATHER #(~/.config/tmux/scripts/weather.sh #{@karsin_tmux_weather_location})  %H:%M "'

setw -g window-status-format "#[fg=#6c7086,bg=#282a36] #I:#W#F "
setw -g window-status-current-format "#[fg=#282a36,bg=#cba6f7,bold] #I:#W#F "
setw -g window-status-style "fg=#6c7086,bg=#282a36"
setw -g window-status-current-style "fg=#282a36,bg=#cba6f7,bold"
setw -g window-status-bell-style "fg=#f8f8f2,bg=#ff5555,bold"

set -g window-style "fg=#4a4f66,bg=default,dim"
set -g window-active-style "fg=#f8f8f2,bg=default"
set -g pane-border-style "fg=#3a3f56,bg=default"
set -g pane-active-border-style "fg=#bd93f9,bg=default"
setw -g clock-mode-colour "#bd93f9"
setw -g mode-style "fg=#282a36,bg=#bd93f9,bold"
set -g message-style "fg=#282a36,bg=#f1fa8c,bold"
set -g message-command-style "fg=#282a36,bg=#8be9fd,bold"

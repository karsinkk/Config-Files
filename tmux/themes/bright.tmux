# Bright, high-contrast theme for dim terminal profiles.

set -g status-style "fg=#111827,bg=#f8fafc,bold"
set -g status-left "#[fg=#ffffff,bg=#2563eb,bold] #S #[fg=#2563eb,bg=#f8fafc,nobold] "
set -g status-right "#[fg=#111827,bg=#f8fafc,bold] CPU:#{cpu_percentage} #[fg=#475569,bg=#f8fafc,nobold]|#[fg=#111827,bg=#f8fafc,bold] Batt: #{battery_icon} #{battery_percentage} #{battery_remain} #[fg=#ffffff,bg=#0f766e,bold] %d/%m #[fg=#ffffff,bg=#dc2626,bold] %H:%M:%S "

setw -g window-status-format "#[fg=#475569,bg=#e2e8f0] #I:#W#F "
setw -g window-status-current-format "#[fg=#111827,bg=#facc15,bold] #I:#W#F "
setw -g window-status-style "fg=#475569,bg=#e2e8f0"
setw -g window-status-current-style "fg=#111827,bg=#facc15,bold"
setw -g window-status-bell-style "fg=#ffffff,bg=#dc2626,bold"

set -g window-style "fg=#64748b,bg=default,dim"
set -g window-active-style "fg=#111827,bg=default"
set -g pane-border-style "fg=#64748b,bg=default"
set -g pane-active-border-style "fg=#2563eb,bg=default"
setw -g clock-mode-colour "#2563eb"
setw -g mode-style "fg=#ffffff,bg=#2563eb,bold"
set -g message-style "fg=#111827,bg=#facc15,bold"
set -g message-command-style "fg=#ffffff,bg=#2563eb,bold"

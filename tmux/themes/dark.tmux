# Dark theme with bright foregrounds and no dim attributes.

set -g status-style "fg=#f9fafb,bg=#111827,bold"
set -g status-left "#[fg=#111827,bg=#22d3ee,bold] #S #[fg=#22d3ee,bg=#111827,nobold] "
set -g status-right "#[fg=#f9fafb,bg=#111827,bold] CPU:#{cpu_percentage} #[fg=#94a3b8,bg=#111827,nobold]|#[fg=#f9fafb,bg=#111827,bold] Batt: #{battery_icon} #{battery_percentage} #{battery_remain} #[fg=#111827,bg=#a7f3d0,bold] %d/%m #[fg=#111827,bg=#f9a8d4,bold] %H:%M:%S "

setw -g window-status-format "#[fg=#cbd5e1,bg=#1f2937] #I:#W#F "
setw -g window-status-current-format "#[fg=#111827,bg=#22d3ee,bold] #I:#W#F "
setw -g window-status-style "fg=#cbd5e1,bg=#1f2937"
setw -g window-status-current-style "fg=#111827,bg=#22d3ee,bold"
setw -g window-status-bell-style "fg=#ffffff,bg=#ef4444,bold"

set -g window-style "fg=#475569,bg=default,dim"
set -g window-active-style "fg=#f9fafb,bg=default"
set -g pane-border-style "fg=#1f2937,bg=default"
set -g pane-active-border-style "fg=#22d3ee,bg=default"
setw -g clock-mode-colour "#22d3ee"
setw -g mode-style "fg=#111827,bg=#22d3ee,bold"
set -g message-style "fg=#111827,bg=#facc15,bold"
set -g message-command-style "fg=#111827,bg=#22d3ee,bold"

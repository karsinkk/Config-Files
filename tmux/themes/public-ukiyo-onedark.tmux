# Ukiyo public multi-theme plugin, OneDark Cool variant.

set -g @ukiyo-theme "onedark/cool"
set -g @ukiyo-plugins "cpu-usage battery time"
set -g @ukiyo-show-powerline true
set -g @ukiyo-show-flags true
set -g @ukiyo-refresh-rate 5
set -g @ukiyo-military-time true
set -g @ukiyo-day-month true

run-shell ~/.config/tmux/plugins/tmux-kanagawa/ukiyo.tmux

bind T display-menu -T "#[align=centre]tmux theme" -x C -y C \
  "Dracula local" d "set -g @karsin_tmux_theme dracula-local \; source-file ~/.tmux.conf" \
  "Ukiyo Kanagawa" u "set -g @karsin_tmux_theme public-ukiyo-kanagawa \; source-file ~/.tmux.conf" \
  "Ukiyo OneDark" o "set -g @karsin_tmux_theme public-ukiyo-onedark \; source-file ~/.tmux.conf" \
  "Theme menu details" m "run-shell ~/.config/tmux/plugins/tmux-kanagawa/menu_items/main.sh"

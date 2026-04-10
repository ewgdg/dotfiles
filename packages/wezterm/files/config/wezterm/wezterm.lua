local wezterm = require 'wezterm'

local config = wezterm.config_builder()

config.color_scheme = 'Everforest Dark (Gogh)'
config.font = wezterm.font_with_fallback {
    'CaskaydiaCove Nerd Font Mono',
    'CaskaydiaCove Nerd Font',
}
config.window_decorations = "INTEGRATED_BUTTONS|RESIZE"

return config

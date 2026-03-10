# Noctalia Pinned Window Widget

This repo adds a small Noctalia plugin at `dotfiles/config/noctalia/plugins/pinned-window`.

It watches the pinned Niri window state from `$XDG_RUNTIME_DIR/niri-pinned-window.json` and listens to `niri msg -j event-stream` so the widget updates without polling. It shows:

- app icon
- window title
- workspace name in the tooltip

Behavior:

- Left click jumps to the pinned window through `pinned-window.sh summon`
- The widget hides itself when no window is pinned
- The source of truth stays in `$XDG_RUNTIME_DIR/niri-pinned-window.json`

Related files:

- `dotfiles/config/niri/bin/pinned-window.sh`
- `dotfiles/config/noctalia/plugins/pinned-window/manifest.json`
- `dotfiles/config/noctalia/plugins/pinned-window/BarWidget.qml`

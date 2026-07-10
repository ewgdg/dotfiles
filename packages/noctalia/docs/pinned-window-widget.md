# Noctalia Pinned Window Widget

This repo adds a Noctalia v5 Luau plugin at
`packages/noctalia/files/local/share/noctalia/plugins/pinned-window`.

It polls `pinned-window.sh status-json` and shows the pinned window title or app
ID. Niri state ownership stays in the existing helper.

- window title, falling back to app ID
- tooltip with summon and clear actions

Behavior:

- left click summons the pinned window
- right click clears the pin
- the widget hides itself when no window is pinned
- the source of truth stays in `pinned-window.sh`

The plugin is enabled as `xian/pinned-window`; the bar widget type is
`xian/pinned-window:window`.

Related files:

- `packages/niri/files/config/niri/bin/pinned-window.sh`
- `packages/noctalia/files/local/share/noctalia/plugins/pinned-window/plugin.toml`
- `packages/noctalia/files/local/share/noctalia/plugins/pinned-window/widget.luau`

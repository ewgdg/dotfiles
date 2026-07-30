# Noctalia Pinned Window Widget

This repo adds a Noctalia v5 Luau plugin at
`packages/noctalia/files/local/share/noctalia/plugins/pinned-window`.

The plugin runs one headless Noctalia service that reads the initial state from
`pinned-window.sh status-json`, follows Niri's event stream, and publishes the
current pinned window through Noctalia shared state. Every bar instance renders
that shared state without polling or starting its own subprocesses. Niri state
ownership stays in the existing helper.

- window title, falling back to app ID
- tooltip with summon and clear actions

Behavior:

- left click summons the pinned window
- right click clears the pin
- the widget hides itself when no window is pinned
- pin, toggle, and clear commands notify the service for immediate updates
- title changes and window closure update from Niri events
- the source of truth stays in `pinned-window.sh`

The headless entry is a Noctalia plugin service, not a separate systemd unit. It
starts and stops with the shell managed by `niri-shell.service`.

The plugin is enabled as `xian/pinned-window`; the bar widget type is
`xian/pinned-window:window`.

Related files:

- `packages/niri/files/config/niri/bin/pinned-window.sh`
- `packages/noctalia/files/local/share/noctalia/plugins/pinned-window/plugin.toml`
- `packages/noctalia/files/local/share/noctalia/plugins/pinned-window/service.luau`
- `packages/noctalia/files/local/share/noctalia/plugins/pinned-window/widget.luau`

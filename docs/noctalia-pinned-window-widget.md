# Noctalia Pinned Window Widget

This repo adds a small Noctalia plugin at
`packages/noctalia/files/config/noctalia/plugins/pinned-window`.

It watches the pinned Niri window state from
`$XDG_RUNTIME_DIR/niri-pinned-window.json` and listens to
`niri msg -j event-stream` so the widget updates without polling. It shows:

- app icon
- window title
- workspace name in the tooltip

Behavior:

- left click jumps to the pinned window through `pinned-window.sh summon`
- the widget hides itself when no window is pinned
- the source of truth stays in `$XDG_RUNTIME_DIR/niri-pinned-window.json`

Implementation note:

- The widget hydrates an initial `niri msg -j windows` and
  `niri msg -j workspaces` snapshot so a newly pinned window can render
  immediately.
- After the initial snapshot it keeps tracking Niri IPC updates from
  `event-stream`, including `WindowsChanged`, `WindowOpenedOrChanged`, and
  `WindowClosed`.
- Outside a Niri session, or when `$NIRI_SOCKET` is missing, the widget stays
  hidden and does not start `niri msg` processes. If the environment variable is
  stale and no socket exists at that path, the guarded process exits quietly.

Related files:

- `packages/niri/files/config/niri/bin/pinned-window.sh`
- `packages/noctalia/files/config/noctalia/plugins/pinned-window/manifest.json`
- `packages/noctalia/files/config/noctalia/plugins/pinned-window/BarWidget.qml`

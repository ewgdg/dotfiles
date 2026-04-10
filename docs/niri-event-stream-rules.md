# Niri Event Stream Rules

This repo adds a small Niri watcher that listens to `niri msg -j event-stream`
and applies declarative rules from `event-stream-rules.json`.

Current capabilities:

- triggers on focus changes and window-opened events
- maintains an in-memory window snapshot from `event-stream` instead of polling
  `focused-window`
- hot-reloads the rules file on mtime change
- compiles regex matchers once per rules reload
- matches against the previously focused window and the currently focused window
- supports literal equality and regex matches
- supports `close-window` actions targeting either the previous or current window
- supports `move-window-to-workspace` actions

Rule file:

- `packages/niri/files/config/niri/event-stream-rules.json`

Related files:

- `packages/niri/files/config/niri/bin/event-stream-rules.py`
- `packages/niri/files/config/systemd/user/niri-event-stream-rules.service`
- `packages/niri/files/config/niri/cfg/switch-events.kdl`

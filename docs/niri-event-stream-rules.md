# Niri Event Stream Rules

This repo adds a small Niri watcher that listens to `niri msg -j event-stream` and applies declarative rules from `event-stream-rules.json`.

Current capabilities:

- Triggers on focus changes and window-opened events
- Maintains an in-memory window snapshot from `event-stream` instead of polling `focused-window`
- Hot-reloads the rules file on mtime change
- Compiles regex matchers once per rules reload
- Matches against the previously focused window and the currently focused window
- Supports literal equality and regex matches
- Supports `close-window` actions targeting either the previous or current window
- Supports `move-window-to-workspace` actions

Rule file:

- `dotfiles/config/niri/event-stream-rules.json`

Related files:

- `dotfiles/config/niri/bin/event-stream-rules.py`
- `dotfiles/config/systemd/user/niri-event-stream-rules.service`
- `dotfiles/config/niri/cfg/switch-events.kdl`

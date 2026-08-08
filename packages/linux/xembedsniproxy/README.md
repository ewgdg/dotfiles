# linux/xembedsniproxy

XEmbed → StatusNotifierItem tray bridge for Wayland. Package id is the family
name (XEmbed-to-SNI proxies); it currently ships `wine-sni-bridge`
(<https://github.com/waliori/wine-sni-bridge>), superseding `xembsni`
(<https://github.com/jmylchreest/xembsni>) which could spawn a black,
unmatchable window under niri.

Bridges legacy X11/Wine/Proton system-tray icons (Battle.net, etc.) into
`waybar`'s `tray` module under niri/Hyprland/sway.

## Why the niri window rule

Unlike `xembsni` (override-redirect windows, no WM_CLASS), `wine-sni-bridge`
uses a **managed** window with `WM_CLASS=wine-sni-bridge` and
`_NET_WM_WINDOW_TYPE_UTILITY`, so it can be stashed with a niri `window-rule`
(`app-id=^wine-sni-bridge$` → stash workspace, no focus).

## Notes

- Single-file Python daemon, vendored into the repo
  (`files/local/bin/wine-sni-bridge.py`) so it can be patched directly; pushed
  to `~/.local/bin` as-is.
- Requires `python-xlib`, `python-dbus`, `python-gobject` (installed via
  pacman on push).
- Runs as `xembedsniproxy.service` (user, bound to `graphical-session.target`).
- Leftover `~/.local/bin/xembsni` from the previous tool is removed manually.

## Updating the vendored script

Vendored at upstream commit `676c5dd2b932` **with local bug fixes** (see git log
for `wine-sni-bridge.py`): alpha/chroma-key handling, crop on the alpha byte,
map/unmap → Active/Passive instead of undocking, capped extraction retries,
clean exit when another tray owns the selection. Re-apply these when syncing.

```sh
curl -fsSL https://raw.githubusercontent.com/waliori/wine-sni-bridge/main/wine-sni-bridge.py \
  -o packages/linux/xembedsniproxy/files/local/bin/wine-sni-bridge.py
```

Review the diff, keep any local patches, then update the commit note above.

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

- Vendored as `wine_sni_bridge.py` + `pyproject.toml` at the package root;
  installed with `uv tool install --editable` (console script
  `wine-sni-bridge` in `~/.local/bin`). Edits to the repo file apply
  immediately without reinstall; the tool resolves the repo path, so the
  dotfiles checkout must stay at the recorded location. Python deps
  (`python-xlib`, `dbus-python`, `PyGObject`) come from PyPI — no pacman
  python packages. First build needs the usual system build deps (gcc,
  pkg-config, dbus/gobject-introspection/cairo headers).
- Runs as `xembedsniproxy.service` (user, bound to `graphical-session.target`).
  IconPixmap defaults to `--byte-order network` (the SNI spec's A,R,G,B
  order), which is what every host decodes — waybar, noctalia, Quickshell,
  KDE (verified in their sources). The upstream `native` default was the
  outlier and rendered color-swapped icons in noctalia.
- Leftover `~/.local/bin/xembsni` from the previous tool is removed manually.

## Updating the vendored script

Vendored at upstream commit `676c5dd2b932` **with local bug fixes** (see git log
for `wine-sni-bridge.py`): alpha/chroma-key handling, crop on the alpha byte,
map/unmap → Active/Passive instead of undocking, capped extraction retries,
clean exit when another tray owns the selection. Re-apply these when syncing.

```sh
curl -fsSL https://raw.githubusercontent.com/waliori/wine-sni-bridge/main/wine-sni-bridge.py \
  -o packages/linux/xembedsniproxy/wine_sni_bridge.py
```

Review the diff, keep any local patches, then update the commit note above.

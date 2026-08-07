# linux/xembedsniproxy

XEmbed → StatusNotifierItem tray bridge for Wayland. Package id is the family
name (XEmbed-to-SNI proxies); it currently ships `xembsni`
(<https://github.com/jmylchreest/xembsni>), superseding the former
`xembed-sni-proxy` (from `somegit.dev/vikingowl`).

Bridges legacy X11/Wine/Proton system-tray icons (Battle.net, etc.) into
`waybar`'s `tray` module under niri/Hyprland/sway.

## Why no niri window rule

The old proxy mapped a normal on-screen X11 window, so niri needed a
`window-rule` to stash it. `xembsni` keeps its windows offscreen with
`override_redirect` set (visible only to Xwayland, surfaced as an unmanaged
popup), so no rule is required. Drop the old `^xembed-sni-proxy$` rule if it
survives in your config.

## Notes

- Binary installs to `~/.local/bin/xembsni` via `cargo install --root` (matches
  upstream's `make install` layout; `~/.local/bin` is on `PATH`).
- Runs as `xembedsniproxy.service` (user, bound to `graphical-session.target`),
  renamed from upstream's `xembsni.service` to match the package family id.
- If another tray already owns the `_NET_SYSTEM_TRAY_S<n>` selection (e.g.
  Plasma's own proxy), `xembsni` exits cleanly rather than fighting — this is
  why the old unit's KDE exclusion was dropped.
- Superseded `xembed-sni-proxy.service` and `~/.cargo/bin/xembed-sni-proxy` are
  removed manually (not handled by this package).

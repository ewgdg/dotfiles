# Mango experiment

Minimal MangoWM trial config drafted to mimic core Niri habits without reimplementing Niri helper scripts.

## Tracked files

- `~/.config/mango/config.conf`
- `~/.config/xdg-desktop-portal/mango-portals.conf`

Source package:

- `packages/mango-experiment/`

## Intentional simplifications

- Mango numeric tags replace Niri named workspaces.
- Mango `toggleglobal` replaces Niri pin/unpin as closest native behavior.
- Mango `scroller` layout is used on all tags as closest native layout to Niri columns.
- Session environment stays in Mango config via `env=` lines, one `exec-once` call to `dbus-update-activation-environment`, and one `exec-once` shell chain that starts `qs -c noctalia-shell`, waits for the tray host, then starts `graphical-session.target` / `xdg-desktop-autostart.target` so user services like Sunshine actually launch.
- Noctalia app launcher is kept via the same `qs -c noctalia-shell ipc call launcher toggle` action used in Niri.
- Portal override keeps Mango's stock `wlr` screencast/screenshot setup and prefers KWallet for `org.freedesktop.impl.portal.Secret`.

## Tag map

- `1` main
- `2` stash
- `3` notes
- `4` AI
- `5` logs
- `6` games
- `7-9` spare

## Xwayland and scaling observations

- Mango's Xwayland support was more stable than Niri in this trial.
- Mango's built-in Xwayland fractional scaling can downscale effective resolution and make Xwayland apps look blurry.
- Mango docs recommend avoiding global Mango scale for mixed Wayland/Xwayland use.
- For Wayland apps, scale with toolkit/user settings instead: Qt DPI, GTK DPI, and GNOME text-size settings.
- Mango docs suggest `xwayland-satellite` for Xwayland scaling when needed.
- In this trial, `xwayland-satellite` worked well enough under Mango and did not show the freezing issue previously seen under Niri.
- Manual test flow used:
  - Start satellite after Mango starts: `xwayland-satellite :2`
  - Run X11 clients through that server: `env DISPLAY=:2 app`
  - For apps that can run as native Wayland clients, force the X11 backend too when needed so the test actually uses satellite.

## Known TODOs left in config

- ctrl:nocaps equivalent, if Mango documents xkb options support
- summon pinned window / move beside pinned
- maximize-on-open window rules
- fcitx / Steam toast special-case rules
- focus-between-floating-and-tiling
- tabbed-column equivalent
- screenshot key integration

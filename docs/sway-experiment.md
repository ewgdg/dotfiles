# Sway experiment

Minimal Sway trial config drafted to mimic core Niri/Mango habits without reimplementing Niri helper scripts.

## Tracked files

- `~/.config/sway/config`
- `~/.config/xdg-desktop-portal/sway-portals.conf`

Source package:

- `packages/sway-experiment/`

## Intentional simplifications

- Sway numeric workspaces replace Niri named workspaces and Mango tags.
- Sway scratchpad replaces Niri pin/stash helpers as the closest native behavior.
- Sway config starts `sway-shell.service`; that service requests `graphical-session.target` / `xdg-desktop-autostart.target` as dependencies, starts Noctalia, then waits for the tray host through `ExecStartPost` before those targets continue.
- greetd uses `vars.desktop.session_command = "/usr/local/bin/start-sway"` for this profile. The wrapper sources `~/.config/sway/session.env`, imports every variable defined there into dbus/systemd, then starts `sway --unsupported-gpu`. Sway config still imports runtime-only display vars (`WAYLAND_DISPLAY`, `DISPLAY`, `SWAYSOCK`) after Sway starts.
- Noctalia app launcher is kept via `Mod+Space` using the same `qs -c noctalia-shell ipc call launcher toggle` action used in Niri and Mango.
- Portal override uses `xdg-desktop-portal-wlr` for screencast/screenshot and prefers KWallet for `org.freedesktop.impl.portal.Secret`.

## Workspace map

- `1` main
- `2` stash
- `3` notes
- `4` AI
- `5` logs
- `6` games
- `7-9` spare

## Related profile/group

Use the Sway-specific host binding when you want Sway plus matching Sunshine config:

- `main:host/linux-sway-meta@host/linux-sway`

This meta package depends on `host/linux-sway`, matching the existing `host/linux-niri-meta` pattern.

For a narrower push, track `main:sway-experiment@host/linux-sway` and `main:sunshine@host/linux-sway`.

## Known TODOs left in config

- direct pinned-window summon / move-beside-pinned behavior
- maximize-on-open rules
- fcitx / Steam toast special-case rules after Sway app_id/title values are observed

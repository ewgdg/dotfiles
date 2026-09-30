# Hyprland experiment

Minimal Hyprland trial config drafted to mimic core Niri/Sway habits without porting Niri helper scripts.

## Tracked files

- `~/.config/hypr/hyprland.lua`
- `~/.config/hypr/drm_device.lua` (rendered with the selected render GPU)
- `~/.config/xdg-desktop-portal/hyprland-portals.conf`
- `~/.config/systemd/user/hyprland.service`
- `~/.config/systemd/user/hyprland-shell.service`
- `/usr/local/bin/hyprland-session`
- `/usr/local/share/wayland-sessions/hyprland.desktop`

Source package:

- `packages/hyprland-experiment/`

## Version target

- Targets Hyprland `0.56.x` Lua config (`hyprland.lua`). Hyprland loads `hyprland.lua` in preference to a leftover `hyprland.conf`.
- `hyprctl keyword` is rejected under Lua config; use `hyprctl eval '<lua>'` for runtime changes (e.g. `hyprctl eval 'hl.monitor({...})'`).
- Validate edits without a session: `Hyprland --verify-config -c ~/.config/hypr/hyprland.lua`.

## Fullscreen and floating windows

- `Mod+F`/`Mod+M` (maximize) and `Mod+Shift+F` (fullscreen) are layout-handled on the scrolling layout: the window stays a column you can scroll away from and back to, like Niri.
- **Failed exam (Hyprland `0.56.2`, still present on upstream `main` in 2026-09):** floats that already exist on the workspace when a window is maximized or fullscreened go under it permanently. Focusing such a float only flashes it before it drops back.
  - Cause: `CScrollingFullscreenHandler::setNoMembersAboveFullscreen()` records those floats in `hiddenFloatingWindowsUnderFSWindow` and re-hides them on every layout recalculation. Nothing removes a float from that set, and focus raises are overwritten by the next recalculation.
  - Maximize and fullscreen share the path. On a scrolling workspace no config option or dispatcher flag avoids it, and Lua cannot reach the set, so a Lua workaround (`fullscreen_float_fix.lua`) was tried and removed.
  - Only fix: patch Hyprland to drop a float from the set when it gets focus.
- Hyprland stays a trial until it passes this; Niri remains the daily session.

## Intentional simplifications

- Hyprland native `scrolling` layout replaces Niri columns as the main experiment path.
- Numeric workspaces replace Niri named workspaces.
- Hyprland special workspace replaces Niri pin/stash helpers as the closest native behavior.
- No Niri helper scripts are copied into this package.
- Noctalia launcher, lock, media, volume, and brightness actions use the v5 `noctalia msg ...` CLI.
- Portal override prefers `xdg-desktop-portal-hyprland`, uses GTK portal for file chooser (path entry via `Ctrl+L`, `/`, and `~`), and uses KWallet for `org.freedesktop.impl.portal.Secret`.

## Dropped in the 0.56 port

- `Mod+Shift+Z` (workspace all-float): Hyprland 0.56 has no `workspaceopt allfloat` dispatcher.
- Scrolling mode `R` (toggle center-vs-fit): upstream removed the `togglefit` layout message.
- `misc:on_focus_under_fullscreen`: has no effect on layout-handled fullscreen.

## Workspace map

- `1` stash
- `2` games
- `3` AI
- `4` notes
- `5` logs
- `6` main
- `7-9` spare
- `special:stash` scratchpad-style native stash

## Keybind highlights

- `Mod+Space`: Noctalia launcher
- `Mod+Shift+Space`: Noctalia window launcher
- `Mod+Return`: terminal
- `Mod+H/L` or arrows: scrolling-layout focus left/right
- `Mod+J/K`: focus down/up
- `Mod+Ctrl+H/L`: swap current scrolling column left/right
- `Mod+U/I`: next/previous open workspace
- `Mod+S/N/A`: stash/notes/AI workspaces (`1`/`4`/`3`, matching Niri named workspace intent)
- `Mod+P` or `Mod+O`: toggle special stash workspace
- `Mod+Shift+P`: move focused window to special stash workspace
- `Mod+Comma/Period`: jump to first/last column (scrolling focus does not wrap)
- `Mod+R`: enter scrolling mode

Scrolling mode (`Mod+R`):

- `H/L` or left/right: move viewport by one column
- `J/K` or down/up: focus down/up
- `Comma/Period`: swap column left/right
- `Minus/Equal`: resize active column
- `Backspace`: reset active column width to `0.5`
- `F/A/V`: fit active/all/visible
- `Return` or `Escape`: exit mode

## Session

Hyprland runs as a systemd user session, mirroring `niri-session`:

- The package's `/usr/local/share/wayland-sessions/hyprland.desktop` runs `/usr/local/bin/hyprland-session`. It overrides the stock `hyprland.desktop` (`Exec=start-hyprland`), because greetd's helper and tuigreet search `/usr/local/share` before `/usr/share`. Like `niri.desktop`, this needs no `session_command`.
- `hyprland-session` re-execs through a login shell, imports the whole login environment into systemd and D-Bus, and waits on `hyprland.service`.
- `hyprland.service` runs `start-hyprland` and is bound to `graphical-session.target`, so Sunshine, the tray proxy, and XDG autostart start with the session.
- Readiness: the unit disables Hyprland's own `READY=1` (`HYPRLAND_NO_SD_NOTIFY=1`), which fires before the session env reaches systemd. `hyprland.lua` creates the Sunshine output, imports the env (`--all`), then runs `systemd-notify --ready`.
- `hyprland-shell.service` (Noctalia) is bound to `hyprland.service` like `niri-shell.service`, and holds XDG autostart until its tray host is up.
- On exit the launcher stops `graphical-session.target`, so session services stop with Hyprland instead of leaking into the next login.
- If the `systemd-notify` step never runs (for example a broken `hyprland.lua`), systemd kills Hyprland after the default start timeout. SSH stays the way in.

## Related profile/group

Use the Hyprland-specific host binding when you want Hyprland plus matching Sunshine config:

- `main:host/linux-hyprland-meta@host/linux-hyprland`

### Trial on a Niri host

To try Hyprland without retracking the Niri host group, keep `main:host/linux-niri-meta@host/linux-niri` tracked and switch the session locally:

- Add to `~/.config/dotman/repos/main/local.toml`:

  ```toml
  [vars.desktop]
  session = "hyprland"
  ```

  Only `packages/greetd` (autologin session) and `packages/linux/sunshine` read `vars.desktop.session`. Confirm the override with `dotman info var desktop.session`.
- Track `main:hyprland-experiment@host/linux-niri`, then `dotman push` twice. The first push installs Hyprland; greetd's guard skips greetd until `hyprland.desktop` exists. The second push points autologin at Hyprland.
- Go back: remove the override and `dotman push`. The Niri config stays deployed throughout.

## Sunshine

`packages/linux/sunshine` renders one Jinja template at `packages/linux/sunshine/files/sunshine.conf` to `~/.config/sunshine/sunshine.conf`.
Because this profile sets `vars.desktop.session = "hyprland"`, the rendered config matches Niri: `capture = wlr`, `output_name = sunshine`, and `sunshine-prep-hyprland.py` with `--headless` / `undo --dormant-headless`.

- `hyprland.lua` creates the fixed `sunshine` headless output at startup (`1920x1080@60`, scale `1`); the prep script resizes it per stream and parks it at 60 Hz afterwards.
- On a headless host this output is the only display, so Sunshine is the only way in: keep SSH working before switching the login session to Hyprland.
- `drm_device.lua` pins Hyprland to the auto-selected render GPU, the one Sunshine captures and encodes on, by setting `AQ_DRM_DEVICES` to its resolved `/dev/dri/cardN`. Rule and override: `docs/render-gpu.md`.

  Without it aquamarine makes the boot-VGA GPU primary. On this host that is the AMD iGPU, which cannot import Sunshine's NVIDIA screencopy buffers, so every stream fails.
- Details and checks: `packages/linux/sunshine/docs/prep-hypr.md`.

## Known TODOs left in config

- Direct pinned-window summon / move-beside-pinned behavior.
- Stronger maximize-on-open rules after observing Hyprland `hyprctl clients` values.
- Fcitx / Steam toast special-case rules after observing class/title values.

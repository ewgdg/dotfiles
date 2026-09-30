# Hyprland experiment

Minimal Hyprland trial config drafted to mimic core Niri/Sway habits without porting Niri helper scripts.

## Tracked files

- `~/.config/hypr/hyprland.lua`
- `~/.config/hypr/fullscreen_float_fix.lua`
- `~/.config/xdg-desktop-portal/hyprland-portals.conf`
- `~/.config/systemd/user/hyprland-shell.service`

Source package:

- `packages/hyprland-experiment/`

## Version target

- Targets Hyprland `0.56.x` Lua config (`hyprland.lua`). Hyprland loads `hyprland.lua` in preference to a leftover `hyprland.conf`.
- `hyprctl keyword` is rejected under Lua config; use `hyprctl eval '<lua>'` for runtime changes (e.g. `hyprctl eval 'hl.monitor({...})'`).
- Validate edits without a session: `Hyprland --verify-config -c ~/.config/hypr/hyprland.lua`.

## Fullscreen and floating windows

- `Mod+F`/`Mod+M` (maximize) and `Mod+Shift+F` (fullscreen) are layout-handled on the scrolling layout: the window stays a column you can scroll away from and back to, like Niri.
- Hyprland `0.56` mishandles floats over a layout-handled fullscreen window: a float opened after the fullscreen stays drawn above it after refocusing the fullscreen window, and a float that existed before stays hidden even when focused.
- `fullscreen_float_fix.lua` works around it: focusing a float raises it over the fullscreen window; focusing the fullscreen window lowers all non-pinned floats on that workspace.
- Remove the module once upstream fixes `ScrollingFullscreenHandler` / `FocusState::fullWindowFocus()` for layout-managed fullscreen.

## Intentional simplifications

- Hyprland native `scrolling` layout replaces Niri columns as the main experiment path.
- Numeric workspaces replace Niri named workspaces.
- Hyprland special workspace replaces Niri pin/stash helpers as the closest native behavior.
- No Niri helper scripts are copied into this package.
- Hyprland starts through the stock `hyprland.desktop` runtime session lookup; no wrapper is installed.
- Hyprland config imports runtime Wayland/Hyprland variables into D-Bus/systemd, then starts `hyprland-shell.service`.
- `hyprland-shell.service` starts Noctalia and waits for the tray host before graphical/autostart targets continue.
- Noctalia launcher, lock, media, volume, and brightness actions use the v5 `noctalia msg ...` CLI.
- Portal override prefers `xdg-desktop-portal-hyprland`, uses GTK portal for file chooser (path entry via `Ctrl+L`, `/`, and `~`), and uses KWallet for `org.freedesktop.impl.portal.Secret`.

## Dropped in the 0.56 port

- `Mod+Shift+Z` (workspace all-float): Hyprland 0.56 has no `workspaceopt allfloat` dispatcher.
- Scrolling mode `R` (toggle center-vs-fit): upstream removed the `togglefit` layout message.
- `misc:on_focus_under_fullscreen`: has no effect on layout-handled fullscreen; `fullscreen_float_fix.lua` covers the float case.

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

## Related profile/group

Use the Hyprland-specific host binding when you want Hyprland plus matching Sunshine config:

- `main:host/linux-hyprland-meta@host/linux-hyprland`

For a narrower push, track `main:hyprland-experiment@host/linux-hyprland` and `main:linux/sunshine@host/linux-hyprland`.

## Sunshine

`packages/linux/sunshine` renders one Jinja template at `packages/linux/sunshine/files/sunshine.conf` to `~/.config/sunshine/sunshine.conf`.
Because this profile sets `vars.desktop.session = "hyprland"`, the rendered config uses `capture = kms` and shared KMS prep args (`--solo --scale dpi-auto --inhibit`) with `sunshine-prep-hyprland.py`, leaving output mode at the script's detected-output default. The inhibitor is only rendered for KMS capture to avoid DPMS error spam when outputs idle mid-stream.

Do not force `--mode headless` unless retesting proves Sunshine can capture Hyprland headless outputs on this machine.

## Known TODOs left in config

- Direct pinned-window summon / move-beside-pinned behavior.
- Stronger maximize-on-open rules after observing Hyprland `hyprctl clients` values.
- Fcitx / Steam toast special-case rules after observing class/title values.

# Hyprland experiment

Minimal Hyprland trial config drafted to mimic core Niri/Sway habits without porting Niri helper scripts.

## Tracked files

- `~/.config/hypr/hyprland.conf`
- `~/.config/xdg-desktop-portal/hyprland-portals.conf`
- `~/.config/systemd/user/hyprland-shell.service`

Source package:

- `packages/hyprland-experiment/`

## Version target

- Targets Arch stable Hyprland `0.54.x`, which still uses `hyprland.conf`.
- Upstream Hyprland `0.55+` moves toward `hyprland.lua`; do not switch this host to `hyprland-git` until the package is ported.

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
- `Mod+R`: enter scrolling mode

Scrolling mode (`Mod+R`):

- `H/L` or left/right: move viewport by one column
- `J/K` or down/up: focus down/up
- `Comma/Period`: swap column left/right
- `Minus/Equal`: resize active column
- `Backspace`: reset active column width to `0.5`
- `F/A/V`: fit active/all/visible
- `R`: toggle center-vs-fit focus behavior
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

- Port to `hyprland.lua` once Arch stable moves to Hyprland `0.55+`.
- Direct pinned-window summon / move-beside-pinned behavior.
- Stronger maximize-on-open rules after observing Hyprland `hyprctl clients` values.
- Fcitx / Steam toast special-case rules after observing class/title values.

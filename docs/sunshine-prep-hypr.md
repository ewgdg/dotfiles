Sunshine Prep (Hyprland)

Overview
- Purpose: prepare Hyprland outputs for Sunshine streaming using a headless output, then restore/cleanup.
- File: `dotfiles/config/sunshine/sunshine-prep-hypr.py`
- Requirements: Hyprland (`hyprctl`) in PATH; optional `ydotool` for a quick wake; `systemd-inhibit` for idle prevention.

Usage
- Create a headless output at a specific mode:
  - `uv run dotfiles/config/sunshine/sunshine-prep-hypr.py do --width 1920 --height 1080 --fps 60`
- Optional: customize name (default `Sunshine-HEADLESS`) and go solo (disable others during session):
  - `uv run dotfiles/config/sunshine/sunshine-prep-hypr.py do --width 2560 --height 1440 --fps 120 --name Sunshine --solo`
- Or rely on Sunshine env vars:
  - `SUNSHINE_CLIENT_WIDTH=1920 SUNSHINE_CLIENT_HEIGHT=1080 SUNSHINE_CLIENT_FPS=60 uv run dotfiles/config/sunshine/sunshine-prep-hypr.py do`
- Restore and cleanup:
  - `uv run dotfiles/config/sunshine/sunshine-prep-hypr.py undo` (uses default name `Sunshine-HEADLESS`)
- If you used a custom name: `uv run dotfiles/config/sunshine/sunshine-prep-hypr.py undo --name Sunshine`

Behavior
- Creates a virtual output via `hyprctl output create headless <name>` and sets `WxH@Fps`.
- `--solo` disables other outputs for the session.
- If headless creation fails, falls back to selecting an existing monitor supporting the mode and disables others.
- Starts `systemd-inhibit` (who: sunshine, what: idle) to keep the session awake.
- `undo` stops the inhibitor, disables any headless outputs, and re-enables physical monitors at `preferred, auto, 1`.
 - Scaling: `--scale` accepts a number or `auto`. In `auto` mode scale is height-based: scale = height / 1080, clamped to [1.0, 3.0] and rounded to 2 decimals (1080→1.0, 1440→1.33, 2160→2.0).
  - If you used a custom headless name not starting with `HEADLESS`, pass it with `--name` to ensure it’s disabled.

Notes
- Headless outputs require Hyprland with `hyprctl output create headless` support (available in modern releases).
- No layout snapshots are stored; restore is best-effort (preferred mode).
- If a mode isn’t supported, the script verifies via `hyprctl -j monitors` and tries alternatives (fallback path).
- The script changes runtime state only; it does not modify your Hyprland config files.

Crashes & Cleanup
- Background guard (default activity mode): `do` starts a guard that watches the headless monitor itself and restores when it goes idle (no mapped clients) for a short grace window.
  - Disable: `--no-guard`.
  - Modes:
    - Activity (default): detects idle headless display; best when Sunshine keeps running as a daemon.
    - Proc/PID: `--guard-mode proc` with `--guard-proc sunshine`, or `--guard-mode pid --pid <PID>`.
  - Tuning: `--guard-interval 5`, `--guard-grace 2`, `--guard-timeout 0`.
  - Monitor selection: the guard watches the same name you pass with `--name` (default `Sunshine-HEADLESS`); you can override with `--guard-monitor`.
  - Fallback awareness: if headless creation fails, the guard auto-switches to `proc` mode to avoid premature cleanup.
- Manual cleanup: you can always run `uv run dotfiles/config/sunshine/sunshine-prep-hypr.py undo`.

Systemd integration (optional)
- If you run Sunshine as a user service, you can make cleanup even more robust:
  - Add a drop-in for `sunshine.service` with `ExecStartPre` to run `do` and `ExecStopPost` to run `undo`, or create a companion service with `PartOf=`/`BindsTo=sunshine.service`.
  - This ensures cleanup executes even on crashes or restarts.

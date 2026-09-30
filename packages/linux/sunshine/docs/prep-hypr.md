# Sunshine Prep (Hyprland)

## Overview

- Purpose: prepare Hyprland outputs for Sunshine streaming. Default mode uses
  an existing detected output; headless output remains experimental for this
  machine because KMS capture may not see it.
- File: `packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py`
- Requirements: Hyprland (`hyprctl`) in PATH; optional `ydotool` for a quick
  wake; optional `systemd-inhibit` for idle prevention.

## Usage

- Create a headless output at a specific mode:
  - `uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py do --width 1920 --height 1080 --fps 60`
- Optional: customize name (default `Sunshine-HEADLESS`) and go solo:
  - `uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py do --width 2560 --height 1440 --fps 120 --name Sunshine --solo`
- Or rely on Sunshine env vars:
  - `SUNSHINE_CLIENT_WIDTH=1920 SUNSHINE_CLIENT_HEIGHT=1080 SUNSHINE_CLIENT_FPS=60 uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py do`
- Restore and cleanup:
  - `uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py undo`
- If you used a custom name:
  - `uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py undo --name Sunshine`

## Behavior

- Default mode selects an existing monitor that supports the requested `WxH@Fps`.
- Headless mode (`--mode headless`) creates a virtual output via `hyprctl output create headless <name>` and sets `WxH@Fps`.
- `--solo` disables other outputs for the session.
- If headless creation fails, falls back to selecting an existing monitor supporting the mode and disables others. If headless creation succeeds but Sunshine cannot capture it, this script cannot detect that failure.
- Starts `systemd-inhibit` (who: sunshine, what: idle) only when `--inhibit` is passed; the rendered Sunshine config passes it for KMS capture to avoid DPMS error spam when outputs idle mid-stream.
- `undo` stops the Sunshine-owned inhibitor, disables any headless outputs, and re-enables physical monitors at `preferred, auto, 1`.
- `--scale` accepts a number or `auto`. In `auto` mode scale is height-based:
  `height / 1080`, clamped to `[1.0, 3.0]` and rounded to 2 decimals.
- If you used a custom headless name not starting with `HEADLESS`, pass it with
  `--name` to ensure it is disabled.

## Notes

- Headless outputs require Hyprland with `hyprctl output create headless` support.
- Monitor changes go through `hyprctl eval 'hl.monitor({...})'`; Hyprland's Lua config (0.56+) rejects `hyprctl keyword`. `hl.monitor` merges into an existing rule for the same output, so the script always sends `disabled` explicitly.
- Hyprland is not wlroots-based but still implements `zwlr_screencopy`, which Sunshine `capture = wlr` uses. Whether a headless output actually renders on this NVIDIA machine is unverified; keep `capture = kms` until the probe below passes.
- No layout snapshots are stored; restore is best-effort.
- If a mode is not supported, the script verifies via `hyprctl -j monitors` and tries alternatives.
- The script changes runtime state only; it does not modify Hyprland config files.

## Virtual display probe

Run once inside a real Hyprland session to decide the virtual-display capture route:

- `packages/linux/sunshine/scripts/probe-hyprland-virtual-display.sh`

It creates a temporary headless output, checks that it gets a size and renders (`grim`), removes it, and prints a verdict:

- headless never gets a size, or does not render → dummy plug + `capture = kms`
- headless renders → `capture = wlr` with a fixed `sunshine` headless output, like Niri

### Findings (Hyprland 0.56.2, aquamarine 0.15.1, NVIDIA)

- Sunshine `capture = wlr` works against Hyprland: it binds `zwlr_screencopy_manager_v1` and `zwp_linux_dmabuf_v1`, selects the headless output by `output_name`, and a Moonlight stream from it connected and decoded frames (tested in a nested Hyprland; the decoded picture itself was not inspected).
- On Hyprland the output description is empty, so Sunshine logs `Selected monitor []`; that is not a failure.
- Nested Hyprland (no DRM backend) cannot allocate headless buffers on NVIDIA: aquamarine's headless fallback format list tags formats with `DRM_FORMAT_INVALID` (0, i.e. `DRM_FORMAT_MOD_LINEAR`), and NVIDIA cannot render to linear buffers. A real DRM session takes headless formats from the DRM backend instead, the same path physical outputs use.

## Crashes and Cleanup

- `do` starts a guard that watches the headless monitor itself and restores when
  it goes idle for a short grace window.
- Disable the guard with `--no-guard`.
- Manual cleanup is always available:
  - `uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py undo`

## Systemd integration

If you run Sunshine as a user service, you can make cleanup more robust with an
`ExecStartPre` / `ExecStopPost` pair or a companion service using `PartOf=` /
`BindsTo=sunshine.service`.

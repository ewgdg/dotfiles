# Sunshine Prep (Hyprland)

## Overview

- Purpose: prepare Hyprland outputs for Sunshine streaming, mirroring the Niri setup.
- Capture: `capture = wlr` with `output_name = sunshine`, a fixed headless output that
  `packages/hyprland-experiment` creates at Hyprland startup (`hyprctl output create headless sunshine`)
  with a default `1920x1080@60`, scale `1` rule.
- File: `packages/linux/sunshine/files/config/sunshine/sunshine-prep-hyprland.py`
- Requirements: Hyprland 0.56+ with a Lua config (`hyprctl`) in PATH; optional `ydotool`
  for a quick wake; optional `systemd-inhibit` for idle prevention.

## Usage

The rendered Sunshine config runs, per stream:

- `sunshine-prep-hyprland.py do --width W --height H --fps F --scale dpi-auto --headless`
- `sunshine-prep-hyprland.py undo --dormant-headless`

Width, height and fps fall back to `SUNSHINE_CLIENT_WIDTH/HEIGHT/FPS`.

## Behavior

- `do --headless` ensures the `sunshine` output exists, sets it to `WxH@F` and the computed
  scale, waits for the mode to apply, then focuses it so remote input lands there.
- `do` without `--headless` picks an existing monitor that supports `WxH@F` (DP first).
- `--solo` disables every other output; `--inhibit` starts `systemd-inhibit` (idle) for KMS capture.
- `do` fails (non-zero exit) when the output is missing or the mode does not apply, so Sunshine
  aborts the stream instead of streaming a wrong mode.
- `undo` stops the inhibitor and re-enables outputs disabled by `--solo`, then:
  - `--dormant-headless`: parks `sunshine` at its current resolution and scale at 60 Hz.
    The output stays present, because disabling it hot-removes the `wl_output`, which
    Wine/XWayland clients see as a monitor unplug on every stream.
  - otherwise: disables `sunshine`.
- `--scale` accepts a number or `auto`/`dpi-auto`: `height / 1080`, clamped to `[1.0, 3.0]`,
  rounded to 2 decimals. Hyprland may nudge it to the nearest scale that divides the mode.
- Monitor changes go through `hyprctl eval 'hl.monitor({...})'`; the Lua config rejects
  `hyprctl keyword`. `hl.monitor` merges into an existing rule for the same output, so the
  script always sends `disabled` explicitly.

## Checks

- After logging into Hyprland: `hyprctl -j monitors all` lists `sunshine` with a non-zero size,
  and `grim -o sunshine /tmp/sunshine.png` produces an image. A 0x0 `sunshine` output means
  headless buffers failed to allocate; see findings below.
- Sunshine logs `Selected monitor []` on Hyprland because output descriptions are empty;
  that is not a failure.

## Findings (Hyprland 0.56.2, aquamarine 0.15.1, NVIDIA)

- Sunshine `capture = wlr` works against Hyprland: it binds `zwlr_screencopy_manager_v1` and
  `zwp_linux_dmabuf_v1`, selects the headless output by `output_name`, and a Moonlight stream
  from it connected and decoded frames (tested in a nested Hyprland; the decoded picture itself
  was not inspected).
- Sunshine's startup encoder check uses dummy frames; it passes even for an output that never
  renders, so it is not a capture test.
- Nested Hyprland (no DRM backend) cannot allocate headless buffers on NVIDIA: aquamarine's
  headless fallback format list tags formats with `DRM_FORMAT_INVALID` (0, i.e.
  `DRM_FORMAT_MOD_LINEAR`), and NVIDIA cannot render to linear buffers. A real DRM session takes
  headless formats from the DRM backend instead, the same path physical outputs use.
- Real DRM session on a hybrid host (AMD iGPU boot VGA + NVIDIA dGPU): aquamarine made the AMD
  GPU primary, so Hyprland rendered on radeonsi. Sunshine's NVIDIA dmabufs then failed to import
  (`eglCreateImageKHR ... createImageFromDmaBufs failed` in `hyprland.log`, `Failed to create buffer
  from params` in Sunshine) and the stream never started. Fix: `vars.hyprland.drm_device` in
  `packages/hyprland-experiment` pins `AQ_DRM_DEVICES` to the NVIDIA card. Lua `hl.env` runs before
  the DRM backend starts, and the value must be a colon-free `/dev/dri/cardN` because
  `AQ_DRM_DEVICES` splits on `:`.
- Monitor rules apply on the next rendered frame, not synchronously with `hyprctl eval`;
  the script polls for the new mode.

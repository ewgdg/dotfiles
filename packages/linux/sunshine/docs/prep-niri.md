# Sunshine Prep (Niri)

- Purpose: create/select/configure the fixed Niri virtual output `sunshine` for
  Sunshine streaming (`WxH@FPS`), optionally turn off other outputs, then
  restore by manually re-enabling connected physical outputs except ones
  explicitly marked `off` in `cfg/output.kdl`, then parking the `sunshine`
  virtual output in a low-power dormant mode.
- Files:
  - `packages/linux/sunshine/files/config/sunshine/sunshine-prep-niri.py`
  - `packages/linux/sunshine/files/sunshine.conf`

## Usage

Run directly inside a running Niri session:

- `uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-niri.py do --width 1920 --height 1080 --fps 60 --solo --scale auto`
- optional: prevent idle actions while streaming with `--inhibit`
- rendered Niri Sunshine config does **not** pass `--inhibit` by default: Niri uses `capture = wlr` on the `sunshine` headless output, while the default inhibitor is only for KMS capture to avoid DPMS error spam when outputs idle mid-stream
- optional: avoid Noctalia/Qt reacting during output hotplug churn with `--suspend-niri-shell`
- Niri Sunshine config uses `--headless`; the fixed output name is `sunshine`
- optional local Niri build: set `vars.niri.bin` in dotman local vars (use `~` for home-relative paths); the rendered Sunshine command exports it as `NIRI_BIN`, and the prep script uses that binary for `niri msg`
- `uv run packages/linux/sunshine/files/config/sunshine/sunshine-prep-niri.py undo`

## Notes

- The script calls `niri msg --json outputs`, picks an output that supports the
  requested mode, then applies:
  - `niri msg output <output> on`
  - `niri msg output <output> mode <WxH@RRR.RRR>`
  - optional: `niri msg output <output> scale <scale>` (`--scale auto` uses Niri auto scaling)
  - optional: turns other outputs `off` when `--solo` is set
  - optional: stops `niri-shell.service` before output changes and runs `systemctl --user reset-failed niri-shell.service` immediately before starting it again when `--suspend-niri-shell` is set
- With `--headless`, the script creates `sunshine` via IPC if needed, then
  reuses and resizes it via `custom-mode`.
- `undo` explicitly turns back on connected outputs, skipping outputs
  explicitly marked `off` in `cfg/output.kdl` and the `sunshine` virtual output,
  then parks `sunshine` at `640x480@30` scale `1` instead of turning it off.
- Reason to park `sunshine` dormant between streams: a persistent high-refresh
  Niri virtual output is suspected to keep Niri/wlroots/NVIDIA-GSP output state
  hot while idle/disconnected, matching observed NVKMS GEM allocation spam
  during the disconnection period plus Sunshine NVENC `InitializeEncoder
  failed: out of memory (10)` / kernel `NVRM NV_ERR_NO_MEMORY` failure. Parking
  keeps `wl_output` present for client stability while reducing render/VRAM
  pressure.
- Reason to use manual IPC instead of config reload: `niri msg action
  load-config-file` can preserve transient IPC output state when disk `outputs`
  did not change, so config reload is not a reliable stream teardown primitive.
  Manual IPC cleanup is the reliable path.
- `sunshine.conf` uses `capture = wlr` and `output_name = sunshine` for Niri
  headless capture; non-Niri rendered configs use `capture = kms`.
- Niri prep keeps `--solo`; `undo` limits restore churn by only re-enabling
  non-Sunshine outputs and explicitly parking the virtual Sunshine output.
- `--suspend-niri-shell` exists but rendered Niri config currently leaves it
  disabled. If enabled for testing, prep stops `niri-shell.service` during stream
  start/undo and runs `systemctl --user reset-failed niri-shell.service`
  immediately before restarting it.
- If explicitly enabled, Noctalia idle inhibition is toggled after `--solo`
  output changes on start and after output restore on undo to avoid notification
  updates racing screen churn.

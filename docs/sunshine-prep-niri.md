# Sunshine Prep (Niri)

- Purpose: create/select/configure the fixed Niri virtual output `sunshine` for
  Sunshine streaming (`WxH@FPS`), optionally turn off other outputs, then
  restore by re-enabling connected outputs except ones explicitly marked `off`
  in `cfg/output.kdl` while keeping the virtual output alive.
- Files:
  - `packages/sunshine/files/config/sunshine/sunshine-prep-niri.py`
  - `packages/sunshine/files/sunshine.conf`

## Usage

Run directly inside a running Niri session:

- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-niri.py do --width 1920 --height 1080 --fps 60 --solo --scale auto`
- optional: prevent idle actions while streaming with `--inhibit` or `SUNSHINE_INHIBIT=1`
- Niri Sunshine config uses `--headless`; the fixed output name is `sunshine`
- optional local Niri build: set `vars.niri.bin` in dotman local vars; the rendered Sunshine command exports it as `NIRI_BIN`, and the prep script uses that binary for `niri msg`
- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-niri.py undo`

## Notes

- The script calls `niri msg --json outputs`, picks an output that supports the
  requested mode, then applies:
  - `niri msg output <output> on`
  - `niri msg output <output> mode <WxH@RRR.RRR>`
  - optional: `niri msg output <output> scale <scale>` (`--scale auto` uses Niri auto scaling)
  - optional: turns other outputs `off` when `--solo` is set
- With `--headless`, the script creates `sunshine` via IPC if needed, then
  reuses and resizes it via `custom-mode`.
- `undo` explicitly turns back on connected outputs, skipping only outputs
  explicitly marked `off` in `cfg/output.kdl`, and intentionally keeps
  `sunshine` alive to avoid hot-removing screens from shell/tray clients.
- `sunshine.conf` uses `capture = wlr` and `output_name = sunshine` for Niri
  headless capture; non-Niri rendered configs use `capture = kms`.
- Niri prep keeps `--solo` but `undo` does not disable `sunshine`; this limits
  output churn to physical-output disable/restore during stream start/stop.
- Noctalia idle inhibition is toggled after `--solo` output changes on start and
  after output restore on undo to avoid notification updates racing screen churn.

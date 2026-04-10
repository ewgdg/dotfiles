# Sunshine Prep (Niri)

- Purpose: select/configure a Niri output for Sunshine streaming (`WxH@FPS`),
  optionally turn off other outputs, then restore on cleanup by reloading Niri
  config and re-enabling all connected outputs except ones explicitly marked
  `off` in `cfg/output.kdl`.
- Files:
  - `packages/sunshine/files/config/sunshine/sunshine-prep-niri.py`
  - `packages/sunshine/files/config/sunshine/sunshine-niri.conf`

## Usage

Run directly inside a running Niri session:

- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-niri.py do --width 1920 --height 1080 --fps 60 --solo --scale auto`
- optional: prevent idle actions while streaming with `--inhibit` or `SUNSHINE_INHIBIT=1`
- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-niri.py undo`

## Notes

- The script calls `niri msg --json outputs`, picks an output that supports the
  requested mode, then applies:
  - `niri msg output <output> on`
  - `niri msg output <output> mode <WxH@RRR.RRR>`
  - optional: `niri msg output <output> scale <scale>` (`--scale auto` uses Niri auto scaling)
  - optional: turns other outputs `off` when `--solo` is set
- `undo` reloads Niri config (best-effort: tries a few IPC variants) and then
  explicitly turns back on connected outputs, skipping only outputs explicitly
  marked `off` in `cfg/output.kdl`.

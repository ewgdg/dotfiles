# Sunshine Prep (COSMIC)

- Purpose: select/configure a COSMIC output for Sunshine streaming (`WxH@FPS`),
  optionally turn off other outputs, then restore connected outputs on cleanup.
- Files:
  - `packages/sunshine/files/config/sunshine/sunshine-prep-cosmic.py`
  - `packages/sunshine/files/config/sunshine/sunshine-cosmic.conf`

## Usage

Run directly inside a running COSMIC session:

- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-cosmic.py do --width 1920 --height 1080 --fps 60 --solo --scale dpi-auto --inhibit`
- optional: force or disable idle prevention with `SUNSHINE_INHIBIT=1` or `SUNSHINE_INHIBIT=0`
- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-cosmic.py undo`

## Notes

- The script calls `cosmic-randr list --kdl`, picks an output that supports the
  requested mode, then applies:
  - `cosmic-randr mode <output> <width> <height> --refresh <Hz>`
  - optional: `--scale <scale>`
  - optional: turns other outputs off with `cosmic-randr disable <output>` when
    `--solo` is set
- `undo` is stateless: it re-enables all currently disabled outputs.
- This keeps cleanup simple but lossy: `undo` does **not** restore prior mode,
  scale, position, transform, mirroring, or XWayland primary state.
- Idle prevention uses a tracked `systemd-inhibit --what=idle sleep infinity`
  process and kills it during `undo`.

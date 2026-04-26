# Sunshine Prep (Sway)

- Purpose: select/configure a Sway output for Sunshine streaming (`WxH@FPS`),
  optionally turn off other outputs, then restore connected outputs on cleanup.
- Files:
  - `packages/sunshine/files/config/sunshine/sunshine-prep-sway.py`
  - `packages/sunshine/files/config/sunshine/sunshine-sway.conf`

## Usage

Run directly inside a running Sway session:

- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-sway.py do --width 1920 --height 1080 --fps 60 --solo --scale dpi-auto --inhibit`
- optional: force or disable idle prevention with `SUNSHINE_INHIBIT=1` or `SUNSHINE_INHIBIT=0`
- `uv run packages/sunshine/files/config/sunshine/sunshine-prep-sway.py undo`

## Notes

- The script calls `wlr-randr --json`, picks an output that supports the
  requested mode, then applies:
  - `wlr-randr --output <output> --on --mode <WxH@Hz>`
  - optional: `--scale <scale>`
  - optional: turns other outputs `off` when `--solo` is set
- If Sunshine crashes after a `--solo` prep run, manually recover with
  `sunshine-prep-sway.py undo` from a shell that can reach the Sway session.
- `undo` is stateless: it re-enables all currently connected outputs.
- Sway idle inhibition is surface-based (`idle_inhibit` criteria), which does
  not fit a windowless Sunshine prep hook. This prep therefore uses Noctalia's
  `idleInhibitor` directly and stores runtime ownership state in
  `$XDG_RUNTIME_DIR`, so a later `do` or `undo` can clear a stale inhibitor left
  behind by a crashed earlier run.
- This keeps the behavior simple but lossy: `undo` does **not** restore prior
  mode, scale, position, or transform.

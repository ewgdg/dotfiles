Sunshine Prep (Niri)

- Purpose: select/configure a Niri output for Sunshine streaming (WxH@FPS), optionally turn off other outputs, then do a simple restore on cleanup by reloading Niri config.
- Files:
  - `dotfiles/config/sunshine/sunshine-prep-niri.py`
  - `dotfiles/config/sunshine/sunshine-niri.conf`

Usage

- Run directly (inside a running Niri session):
  - `uv run dotfiles/config/sunshine/sunshine-prep-niri.py do --width 1920 --height 1080 --fps 60 --solo --scale auto`
  - Optional: prevent idle actions while streaming: add `--inhibit` (or set `SUNSHINE_INHIBIT=1`)
  - `uv run dotfiles/config/sunshine/sunshine-prep-niri.py undo`

Notes

- The script calls `niri msg --json outputs`, picks an output that supports the requested mode, then applies:
  - `niri msg output <output> on`
  - `niri msg output <output> mode <WxH@RRR.RRR>`
  - optional: `niri msg output <output> scale <scale>` (`--scale auto` uses Niri auto scaling)
  - optional: turns other outputs `off` when `--solo` is set
- `undo` does a stateless restore by reloading Niri config (best-effort: tries `niri msg reload-config` then a couple fallbacks).

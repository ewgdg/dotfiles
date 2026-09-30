# Port the Hyprland experiment to Lua, with the fullscreen fix and a virtual display

## Goal

`packages/hyprland-experiment` runs on Arch stable Hyprland 0.56.x as a second
login session next to niri. It ships a Lua config at parity with the old
`hyprland.conf`, a focus hook that makes scrolling-layout fullscreen handle
floating windows correctly, and a Sunshine-streamable virtual display.

## Intention

A one-week trial decides whether to leave niri. The trial is only meaningful if
the known fullscreen defect is neutralised and streaming works the way it does
on niri (fixed virtual output, parked when idle). Niri stays the default and
untouched.

## Scope & Constraints

In scope:

- Replace `hyprland.conf` with `hyprland.lua` (0.55+ prefers `.lua`; `keyword`
  no longer works under Lua, only `hyprctl eval`).
- Separate Lua module for the fullscreen/floating focus workaround.
- Virtual display: fixed headless output named `sunshine`, mirroring niri's
  `output "sunshine" { create-virtual }`.
- Sunshine prep script and rendered `sunshine.conf` for the Hyprland session.
- Package README / Sunshine docs updated; superseded conf-era notes removed.

Out of scope:

- Changing niri, its fork, or the niri Sunshine path.
- Porting niri helper scripts (pinned window etc.).
- Upstream bug report / PR for the fullscreen defect (separate follow-up).

Constraints:

- The user runs `dotman push` and `sudo pacman`; the agent does not.
- No live Hyprland session is available to the agent. Nested Hyprland under
  niri never gets an xdg configure, so it cannot render or screencopy, and
  headless outputs there fail GBM allocation on this NVIDIA RTX 5070 Ti.

## Work Plan

1. Lua config at parity with `hyprland.conf` plus `fullscreen_float_fix.lua`.
   Validate with `Hyprland --verify-config` and the nested harness (binds and
   hook behaviour via `hyprctl repl` state).
2. Virtual display probe script the user runs once in the real session. It
   decides the capture route:
   - headless renders and `grim -o sunshine` works → `capture = wlr`,
     `output_name = sunshine`, same model as niri;
   - headless renders but wlr capture fails → portal capture with an xdph
     `custom_picker_binary` that auto-selects `screen:sunshine` (no dialog);
   - headless never renders (0x0 / GBM failure) → dummy plug + KMS (current
     prep default).
3. Implement the chosen route in the prep script and `sunshine.conf` template.
4. Docs.

## Validation

- `Hyprland --verify-config -c hyprland.lua` reports `config ok`.
- Nested harness: every bind resolves (config load has no errors), the
  fullscreen hook passes early/late float, toggle, recalc and scroll cases.
- Real session (user): probe output, then a Moonlight stream.

## Progress

- [x] Step 1 Lua config + fullscreen hook (verify-config ok; nested 0.56.2: 126/128 binds, 2 intentionally dropped; float fix passes for Mod+F maximize and Mod+Shift+F fullscreen)
- [ ] Step 2 probe script
- [ ] Step 3 capture route
- [ ] Step 4 docs

## Surprises & Discoveries

- Scrolling layout-handled fullscreen ignores focus for floats: focused
  pre-existing float stays hidden; float opened after FS stays above FS window.
  Causes: `FocusState::fullWindowFocus()` skips the float branch when FS is
  layout-managed; `ScrollingFullscreenHandler` recomputes from a snapshot.
- The focus hook must be deferred (`hl.timer`, 1 ms): the scrolling layout's
  own focus listener recomputes the flags after Lua listeners run.
- `hyprctl keyword` is rejected under a Lua config ("Use eval").
- `hl.animation` needs `bezier = "..."` (not `curve`); `--verify-config` catches it.
- Lua `hl.bind` ignores the `mouse` option; `hl.dsp.window.drag()`/`resize()`
  handle button release themselves (`releasePending`).
- Headless output GBM allocation fails in the nested session on NVIDIA
  (XR24, with and without modifiers). Unknown whether a real DRM session
  behaves the same; the probe answers it.
- User previously observed Sunshine `capture = wlr` failing on Hyprland.
  Hyprland still implements `zwlr_screencopy`, which is what Sunshine's wlr
  backend binds, so that failure may have been the headless output never
  rendering rather than the capture protocol.

## Decisions

- Keep the stock `hyprland.desktop` session; no wrapper.
- Fullscreen workaround lives in config, not a fork or plugin, until upstream
  fixes the scrolling fullscreen handler.

## Outcomes & Retrospective

(pending)

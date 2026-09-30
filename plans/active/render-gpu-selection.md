# Render GPU selection

## Goal

Pick one render GPU per Linux host automatically at `dotman push` time and use it
consistently for Niri rendering, Hyprland rendering, and Sunshine capture/encoding.

## Intention

- Compositor, capture buffers, and encoder must share one GPU. A mismatch broke the first
  real Hyprland stream: Hyprland rendered on the AMD iGPU (boot VGA) and could not import
  Sunshine's NVIDIA screencopy dmabufs.
- One rule for both compositors instead of per-compositor host vars.
- No sudo, no vendor tools, no dependence on BIOS boot-GPU choice.

## Scope & Constraints

- In scope: shared helper script, Niri `cfg/debug.kdl`, Hyprland `drm_device.lua`,
  Sunshine `sunshine.conf` (`adapter_name`, `encoder`), docs, tests, local var migration.
- Out of scope: runtime (login-time) detection; multi-dGPU policy beyond failing on ties.
- Unprivileged only: sysfs + Vulkan loader. dotman vars cannot come from commands, so
  targets use a render command that injects detected vars into `dotman render jinja`.
- Fail fast: no GPU or a tie fails the render and names the override.

## Work Plan

1. Tests first for the pure selection rule and sysfs memory-window parsing.
2. `scripts/select_render_gpu.py`:
   - candidates: PCI display devices (class `0x03`) behind `/sys/class/drm/renderD*`;
   - type: Vulkan `deviceType` via `libvulkan` ctypes, mapped by `VK_EXT_pci_bus_info`
     (properties only, no `vkCreateDevice`);
   - memory window: largest prefetchable BAR from sysfs `resource`;
   - rule: discrete pool if any, else all; largest window wins; tie or empty fails;
   - override: `vars.render_gpu.pci` (seen as `DOTMAN_VAR_render_gpu__pci`);
   - `show` explains candidates; `render <source>` execs
     `dotman render jinja --var render_gpu.pci=… --var render_gpu.vendor=… <source>`.
3. Templates use `vars.render_gpu.pci` / `vars.render_gpu.vendor`; manifests switch those files to the
   helper render with patch capture.
4. Sunshine: `adapter_name = /dev/dri/by-path/pci-<pci>-render`; `encoder` by vendor
   (nvidia → nvenc, amd/intel → vaapi).
5. Remove superseded `vars.niri.render_drm_device`, `vars.hyprland.drm_device`, the Niri
   suggest helper and its doc; migrate `local.toml`.

## Validation

- `uv run pytest` for the new tests.
- `scripts/select_render_gpu.py show` on this host picks `0000:01:00.0` (NVIDIA).
- `dotman --unattended push --dry-run` renders the three targets with the NVIDIA paths.
- Real session: Hyprland log shows `Explicit device list /dev/dri/card0`; Moonlight streams.

## Progress

- [x] Tests (`tests/test_select_render_gpu.py`, 12 passing)
- [x] Helper (`show` on this host selects `0000:01:00.0`, NVIDIA, Vulkan discrete, 16384 MiB)
- [x] Templates and manifests (dry-run push renders all three with NVIDIA paths; Hyprland
      config verifies; override and bad-override paths checked)
- [x] Docs (`docs/render-gpu.md`) and migration (`local.toml` old vars removed)
- [ ] Host validation: push, restart greetd, confirm Hyprland primary GPU and Moonlight stream
- [x] Pull after push: `dotman pull --dry-run` reports 61 in sync, no capture failures

## Surprises & Discoveries

- `packages/niri` `post_push` fails while Hyprland is the running session: it starts
  `niri-shell.service`, whose niri dependency is not running. Unrelated to this plan.

- `/sys/bus/pci/slots` misses the x16 slot on this board; slot flags need root.
- NVIDIA exposes no VRAM size in sysfs; prefetchable BAR size (memory window) is readable
  but only separates GPUs with Resizable BAR on.
- `vulkaninfo --summary` fails when `vkCreateDevice` fails; properties enumeration still works.
- Sunshine NVENC always uses CUDA device 0; `adapter_name` drives capture buffers, VAAPI and
  Vulkan encode (`src/platform/linux/misc.cpp` `resolve_render_device`).

## Decisions

- Var name `vars.render_gpu` (user): it scopes rendering; Sunshine follows the render GPU.
- Detection runs inside a render command because dotman vars cannot come from commands;
  the helper reads the override from `DOTMAN_VAR_render_gpu__pci` and passes the result with
  `--var`, which takes precedence over inherited `DOTMAN_VAR_*`.

- Vulkan type first, memory window second (user choice). Vulkan unavailable counts as
  "no discrete" and falls back to the memory window across all GPUs.
- Push-time render, not login-time detection: Niri's KDL config cannot run code.

## Outcomes & Retrospective

TBD.

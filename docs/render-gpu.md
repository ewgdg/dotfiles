# Render GPU

One GPU per Linux host renders the compositor and hosts Sunshine capture and encoding.
They must share it: screencopy dmabufs allocated on one GPU cannot be imported by a
compositor rendering on another (for example an AMD iGPU rendering while Sunshine
captures on an NVIDIA dGPU fails with `createImageFromDmaBufs failed`).

## Selection

`scripts/select_render_gpu.py` picks it at `dotman render` time, without root:

1. Candidates: PCI display devices (class `0x03`) behind `/sys/class/drm/renderD*`.
2. Prefer GPUs whose Vulkan driver reports `VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU`
   (read via physical-device properties and `VK_EXT_pci_bus_info`; no device is created).
   A GPU without a Vulkan driver, or a host without `libvulkan`, counts as untyped.
3. Among discrete GPUs, or among all GPUs when none is discrete, the largest memory window
   (largest prefetchable PCI BAR in sysfs `resource`) wins.
4. No GPU, or a tie on memory window, fails the render.

Why these signals: the boot-VGA flag follows the BIOS primary-display setting, PCIe slot
flags need root, and NVIDIA exposes no VRAM size in sysfs. The memory window only separates
GPUs when Resizable BAR is on, so it is the secondary factor.

Inspect the decision:

```sh
uv run scripts/select_render_gpu.py show
```

## Override

Set the PCI address in `~/.config/dotman/repos/main/local.toml`:

```toml
[vars.render_gpu]
pci = "0000:01:00.0"
```

## Consumers

Each consumer uses a render command that runs the helper, which then calls
`dotman render jinja --var render_gpu.pci=… --var render_gpu.vendor=…`:

- `packages/niri` `cfg/debug.kdl`: `render-drm-device "/dev/dri/by-path/pci-<pci>-render"`.
- `packages/hyprland-experiment` `drm_device.lua`: sets `AQ_DRM_DEVICES` to the resolved
  `/dev/dri/by-path/pci-<pci>-card` (`AQ_DRM_DEVICES` splits on `:`, so it must be `/dev/dri/cardN`).
- `packages/linux/sunshine` `sunshine.conf`: `adapter_name = /dev/dri/by-path/pci-<pci>-render`
  (capture buffers, VAAPI and Vulkan encode) and `encoder` by vendor: `nvidia` → `nvenc`,
  `amd`/`intel` → `vaapi`; other vendors keep autodetection. Sunshine's NVENC path always uses
  CUDA device 0.

The value is fixed at push time: after changing GPUs, push these packages again.

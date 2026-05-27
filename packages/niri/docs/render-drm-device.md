# Niri Render DRM Device

`cfg/debug.kdl` can render `debug.render-drm-device` from the host-local Dotman var:

```toml
[vars.niri]
render_drm_device = "/dev/dri/by-path/pci-...-render"
```

Use a stable `/dev/dri/by-path/*-render` path instead of `/dev/dri/renderD*`, because render node numbers can change between boots.

## Candidate helper

Run:

```sh
packages/niri/scripts/suggest_render_drm_device.py
```

The helper prints all DRM render nodes with PCI/sysfs metadata and a suggested local override when the choice is simple. It does not assume a specific GPU vendor.

The recommendation is conservative:

- one render node: suggest it
- one non-boot-VGA render node plus at least one boot-VGA node: suggest the non-boot-VGA node as a common secondary-GPU hint
- otherwise: no recommendation; choose manually from candidates

For scripts:

```sh
packages/niri/scripts/suggest_render_drm_device.py --value-only
```

`--value-only` exits non-zero when the choice is ambiguous.

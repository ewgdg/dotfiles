-- Pin Hyprland to the render GPU, like Niri's `debug.render-drm-device`.
-- `vars.render_gpu.pci` comes from scripts/select_render_gpu.py at dotman render time
-- (override it in host-local vars).
--
-- Why: on a hybrid host aquamarine makes the boot-VGA GPU primary. When that is the
-- iGPU while Sunshine captures and encodes on the dGPU, the iGPU renderer cannot
-- import the dGPU screencopy dmabufs and every captured frame fails.
-- Must run before anything else: aquamarine reads AQ_DRM_DEVICES when the DRM
-- backend starts, right after the config is first parsed.

local DRM_DEVICE = "/dev/dri/by-path/pci-{{ vars.render_gpu.pci }}-card"

local function resolve_device_node(path)
    -- AQ_DRM_DEVICES is ':'-separated and by-path names contain PCI colons, so pass
    -- the resolved /dev/dri/cardN instead of the stable symlink.
    local handle = io.popen("readlink -e '" .. path .. "'")
    local node = handle:read("l")
    handle:close()
    return node
end

local node = resolve_device_node(DRM_DEVICE)
if node then
    hl.env("AQ_DRM_DEVICES", node)
else
    -- Keep loading the rest of the config: on a headless host an aborted config
    -- also drops the Sunshine output, which is the only way back in.
    io.stderr:write("drm_device.lua: " .. DRM_DEVICE .. " not found; using aquamarine's default GPU\n")
end

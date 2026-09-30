-- Make scrolling-layout (layout-handled) fullscreen treat floating windows by focus,
-- the way default-handled fullscreen already does.
--
-- Hyprland 0.56 defect this works around:
-- - Focusing a floating window that existed before the fullscreen keeps it hidden:
--   FocusState::fullWindowFocus() skips its "raise focused float" branch when the
--   fullscreen is layout-managed.
-- - A floating window opened after the fullscreen stays drawn above it even when the
--   fullscreen window is refocused: ScrollingFullscreenHandler recomputes the
--   "allowed over fullscreen" flag from a snapshot taken at fullscreen time.
-- Remove this module once upstream fixes the scrolling fullscreen handler.

local M = {}

-- The scrolling layout's own focus listener recomputes the flags after Lua listeners
-- run, so applying immediately would be overwritten. 1 ms defers past that recalc.
local APPLY_DELAY_MS = 1

local function layout_fullscreen_window(workspace)
    for _, window in ipairs(hl.get_windows()) do
        if window.workspace == workspace and window.fullscreen > 0 and window.fullscreen_handler == "scrolling" then
            return window
        end
    end
end

local function set_zorder(window, mode)
    hl.dispatch(hl.dsp.window.alter_zorder({ mode = mode, window = "address:" .. window.address }))
end

local function apply_focus_rule(address)
    local focused = hl.get_window("address:" .. address)
    if not focused or not focused.workspace then
        return
    end

    local fullscreen = layout_fullscreen_window(focused.workspace)
    if not fullscreen then
        return
    end

    if focused.floating then
        set_zorder(focused, "top")
    elseif focused.address == fullscreen.address then
        for _, window in ipairs(hl.get_windows()) do
            if window.workspace == focused.workspace and window.floating and not window.pinned then
                set_zorder(window, "bottom")
            end
        end
    end
end

function M.setup()
    hl.on("window.active", function(window)
        if not window then
            return
        end
        local address = window.address
        hl.timer(function() apply_focus_rule(address) end, { timeout = APPLY_DELAY_MS, type = "oneshot" })
    end)
end

return M

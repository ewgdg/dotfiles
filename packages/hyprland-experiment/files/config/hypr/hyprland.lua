-- Hyprland trial config that keeps main Niri/Sway habits.
-- Target: Arch stable Hyprland 0.56.x Lua config (hyprland.lua wins over hyprland.conf).
-- Notes:
-- - Native scrolling layout replaces Niri columns; no Niri helper scripts are ported.
-- - `hyprctl keyword` does not work with a Lua config; use `hyprctl eval '<lua>'`.
-- - Missing native equivalents stay as TODO comments.

local mainMod = "SUPER"
local terminal = "ghostty"
local launcher = "noctalia msg panel-toggle launcher"
local launcherWindows = 'noctalia msg panel-toggle launcher "/win "'

-- Workspace map mirrors Niri declaration order:
-- 1 stash | 2 games | 3 AI | 4 notes | 5 logs | 6 main | 7-9 spare

------------------------------
---- SESSION / ENVIRONMENT ----
------------------------------

require("drm_device")

-- Fixed Sunshine virtual output, like Niri's `output "sunshine" { create-virtual }`.
-- Sunshine captures it with `capture = wlr` / `output_name = sunshine`; its prep script
-- resizes it per stream and parks it between streams instead of removing it.
local SUNSHINE_OUTPUT = "sunshine"
hl.monitor({ output = SUNSHINE_OUTPUT, mode = "1920x1080@60", position = "auto", scale = 1 })
-- No other static monitor rules. Sunshine/runtime monitor control decides output state.
-- Use `hyprctl reload config-only`; a full reload or compositor restart may re-probe outputs.

local sessionEnv = {
    XDG_CURRENT_DESKTOP = "Hyprland",
    XDG_SESSION_TYPE = "wayland",
    XDG_SESSION_DESKTOP = "Hyprland",
    QT_QPA_PLATFORMTHEME = "gtk3",
    QS_ICON_THEME = "Papirus-Dark",
    QT_IM_MODULE = "fcitx",
    QT_IM_MODULES = "wayland;fcitx;ibus",
    XMODIFIERS = "@im=fcitx",
    SDL_IM_MODULE = "fcitx",
    XCURSOR_THEME = "Bibata-Modern-Ice",
}
for name, value in pairs(sessionEnv) do
    hl.env(name, value)
end

-- Runtime display vars only exist after Hyprland starts. Import the whole session env
-- (like niri-session) so portals, user services, and shell-spawned apps agree, and no
-- hand-kept variable list goes stale.
-- Then tell systemd hyprland.service is ready (its unit disables Hyprland's own, earlier
-- READY=1), so hyprland-shell.service and graphical-session.target start only once the
-- env and the Sunshine output exist. Outside hyprland-session there is no NOTIFY_SOCKET,
-- so this step fails harmlessly.
local importEnvAndNotifyReady = "dbus-update-activation-environment --systemd --all; "
    .. "systemd-notify --ready"

hl.on("hyprland.start", function()
    -- No Lua API creates headless outputs. Chain it before readiness (exec_cmd is
    -- async) so bars and portals start against the final output set.
    hl.exec_cmd("hyprctl output create headless " .. SUNSHINE_OUTPUT .. "; " .. importEnvAndNotifyReady)

    -- Native autostart only.
    hl.exec_cmd("launch-desktop-app memos '^chrome-.*-Default[.]desktop$'")
    hl.exec_cmd("obsidian")
    hl.exec_cmd("launch-desktop-app ChatGPT '^chrome-.*-Default[.]desktop$'")
    hl.exec_cmd("launch-desktop-app 'Google AI Studio' '^chrome-.*-Default[.]desktop$'")
    hl.exec_cmd("ghostty --title=logs-journalctl -e journalctl -f -n 20")
end)

------------------------
---- OUTPUT / LOOK ----
------------------------

hl.config({
    general = {
        gaps_in = 5,
        gaps_out = 5,
        border_size = 2,
        col = {
            active_border = "rgba(ffc87fff)",
            inactive_border = "rgba(505050aa)",
        },
        layout = "scrolling",
        -- Stop directional focus at screen edge instead of fallback-focusing.
        no_focus_fallback = true,
        resize_on_border = false,
    },

    scrolling = {
        -- Niri-like default column width and presets, using Hyprland-native layout messages.
        fullscreen_on_one_column = false,
        column_width = 0.5,
        focus_fit_method = 1,
        follow_focus = true,
        follow_min_visible = 0.4,
        explicit_column_widths = "0.333, 0.5, 0.667, 1.0",
        direction = "right",
        -- Niri stops at the ends of the strip; also keeps the Mod+comma/period
        -- "jump to end" loops below from cycling forever.
        wrap_focus = false,
        wrap_swapcol = false,
    },

    decoration = {
        rounding = 12,
        active_opacity = 1.0,
        -- Avoid focus-switch flicker: opacity changes animate every time focus moves.
        inactive_opacity = 1.0,
        blur = { enabled = false },
        shadow = { enabled = false },
    },

    misc = {
        disable_hyprland_logo = true,
        disable_splash_rendering = true,
        force_default_wallpaper = 0,
        background_color = "rgb(000000)",
        -- Config autoreload is off. Reload manually without resetting runtime monitor
        -- state via: hyprctl reload config-only
        disable_autoreload = true,
    },

    binds = {
        -- With a fullscreen window focused, directional focus otherwise jumps to other
        -- monitors instead of moving within the scrolling strip.
        movefocus_cycles_fullscreen = true,
    },

    debug = {
        -- VFR can make repaint artifacts around Chromium/fractional-scale windows more visible.
        vfr = false,
    },

    xwayland = {
        enabled = true,
        force_zero_scaling = true,
    },

    cursor = {
        no_warps = true,
    },
})

hl.animation({ leaf = "windows", enabled = true, speed = 2, bezier = "default" })
hl.animation({ leaf = "windowsMove", enabled = true, speed = 2, bezier = "default" })
hl.animation({ leaf = "fade", enabled = true, speed = 2, bezier = "default" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 2, bezier = "default", style = "slidevert" })
hl.animation({ leaf = "specialWorkspace", enabled = true, speed = 2, bezier = "default", style = "slidevert" })

---------------
---- INPUT ----
---------------

hl.config({
    input = {
        kb_layout = "us",
        kb_options = "ctrl:nocaps",
        repeat_delay = 600,
        repeat_rate = 25,

        follow_mouse = 0,
        sensitivity = 0,
        accel_profile = "flat",

        touchpad = {
            tap_to_click = true,
            tap_and_drag = true,
            disable_while_typing = true,
            natural_scroll = true,
        },
    },
})

hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

--------------------
---- WORKSPACES ----
--------------------

local persistentWorkspaces = { "stash", "games", "AI", "notes", "logs", "main" }
for id, name in ipairs(persistentWorkspaces) do
    hl.workspace_rule({ workspace = tostring(id), default_name = name, persistent = true })
end
for id = 7, 9 do
    hl.workspace_rule({ workspace = tostring(id), default_name = "spare-" .. id })
end

--------------------------------------------------
---- APP PLACEMENT. Keep only simple native rules.
--------------------------------------------------

local placementRules = {
    { name = "steam-games-workspace", match = { class = "^steam$" }, workspace = "2 silent" },
    { name = "faugus-games-workspace", match = { class = "^(lutris|faugus-launcher)$" }, workspace = "2 silent" },
    { name = "battle-net-games-workspace", match = { title = "^Battle\\.net$" }, workspace = "2 silent" },
    { name = "wine-tray-stash-workspace", match = { class = "^explorer\\.exe$" }, workspace = "1 silent" },
    { name = "obsidian-notes-workspace", match = { class = "(?i)^obsidian$" }, workspace = "4 silent" },
    { name = "memos-notes-workspace", match = { title = "^Memos.*$" }, workspace = "4 silent" },
    { name = "chatgpt-ai-workspace", match = { title = "^ChatGPT.*$" }, workspace = "3 silent" },
    { name = "google-ai-studio-workspace", match = { title = "^Google AI Studio.*$" }, workspace = "3 silent" },
    { name = "logs-workspace", match = { title = "^logs-journalctl$" }, workspace = "5 silent" },
    { name = "onepassword-floating", match = { class = "(?i)^1password(-quickaccess)?$" }, float = true, center = true },
    { name = "goldendict-floating", match = { class = "(?i).*goldendict.*" }, float = true, size = "800 600", center = true },
    { name = "floating-border-on", match = { float = true }, border_size = 2 },
}
for _, rule in ipairs(placementRules) do
    hl.window_rule(rule)
end

-- TODO: add stronger maximize-on-open rules after observing Hyprland class/title values.
-- TODO: add Fcitx / Steam toast special cases after observing `hyprctl clients` output.

----------------------
---- KEY BINDINGS ----
----------------------

local function bindMod(keys, dispatcher, flags)
    hl.bind(mainMod .. " + " .. keys, dispatcher, flags)
end

local function layoutMessage(message)
    return hl.dsp.layout(message)
end

-- Applications.
bindMod("Return", hl.dsp.exec_cmd(terminal))
bindMod("space", hl.dsp.exec_cmd(launcher))
bindMod("SHIFT + space", hl.dsp.exec_cmd(launcherWindows))
hl.bind("ALT + Tab", hl.dsp.exec_cmd(launcherWindows))
bindMod("b", hl.dsp.exec_cmd("google-chrome-stable"))
bindMod("d", hl.dsp.exec_cmd("goldendict"))
bindMod("CTRL + d", hl.dsp.exec_cmd("goldendict-search"))
bindMod("e", hl.dsp.exec_cmd("nautilus --new-window"))
bindMod("CTRL + SHIFT + space", hl.dsp.exec_cmd("1password --quick-access"))

-- Noctalia actions.
bindMod("CTRL + SHIFT + l", hl.dsp.exec_cmd("noctalia msg session lock"))
hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("noctalia msg media toggle"), { locked = true })
hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("noctalia msg media previous"), { locked = true })
hl.bind("XF86AudioNext", hl.dsp.exec_cmd("noctalia msg media next"), { locked = true })
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("noctalia msg volume-up"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("noctalia msg volume-down"), { locked = true, repeating = true })
hl.bind("XF86AudioMute", hl.dsp.exec_cmd("noctalia msg volume-mute"), { locked = true })
hl.bind("XF86AudioMicMute", hl.dsp.exec_cmd("noctalia msg mic-mute"), { locked = true })
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("noctalia msg brightness-up"), { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("noctalia msg brightness-down"), { locked = true, repeating = true })

-- Window lifecycle.
bindMod("q", hl.dsp.window.close())
bindMod("SHIFT + c", hl.dsp.exec_cmd("hyprctl reload config-only"))
bindMod("CTRL + SHIFT + Delete", hl.dsp.exit())

-- Focus. Horizontal focus uses scrolling layout messages to keep movement on the strip.
local directions = {
    { keys = { "left", "h" }, name = "left", column = "l" },
    { keys = { "right", "l" }, name = "right", column = "r" },
    { keys = { "down", "j" }, name = "down" },
    { keys = { "up", "k" }, name = "up" },
}
for _, direction in ipairs(directions) do
    for _, key in ipairs(direction.keys) do
        if direction.column then
            bindMod(key, layoutMessage("focus " .. direction.column))
            -- Move/swap columns.
            bindMod("CTRL + " .. key, layoutMessage("swapcol " .. direction.column))
        else
            bindMod(key, hl.dsp.focus({ direction = direction.name }))
            bindMod("CTRL + " .. key, hl.dsp.window.move({ direction = direction.name }))
        end
        -- Monitors.
        bindMod("SHIFT + " .. key, hl.dsp.focus({ monitor = direction.column or direction.name:sub(1, 1) }))
    end
end
for _, direction in ipairs(directions) do
    local monitor = direction.column or direction.name:sub(1, 1)
    bindMod("CTRL + SHIFT + " .. direction.keys[1], hl.dsp.workspace.move({ monitor = monitor }))
end

-- Jump to the first/last column. Stops at the ends because wrap_focus is off.
local STRIP_JUMP_STEPS = 30
local function focusColumnRepeatedly(column)
    return function()
        for _ = 1, STRIP_JUMP_STEPS do
            hl.dispatch(layoutMessage("focus " .. column))
        end
    end
end
bindMod("comma", focusColumnRepeatedly("l"))
bindMod("period", focusColumnRepeatedly("r"))

-- Workspace switching follows positional Vim: u is j/down/next, i is k/up/previous.
bindMod("u", hl.dsp.focus({ workspace = "e+1" }))
bindMod("i", hl.dsp.focus({ workspace = "e-1" }))
bindMod("SHIFT + u", hl.dsp.window.move({ workspace = "e+1" }))
bindMod("SHIFT + i", hl.dsp.window.move({ workspace = "e-1" }))
bindMod("CTRL + u", hl.dsp.window.move({ workspace = "e+1", follow = false }))
bindMod("CTRL + i", hl.dsp.window.move({ workspace = "e-1", follow = false }))
bindMod("mouse_down", hl.dsp.focus({ workspace = "e+1" }))
bindMod("mouse_up", hl.dsp.focus({ workspace = "e-1" }))
bindMod("CTRL + mouse_down", hl.dsp.window.move({ workspace = "e+1", follow = false }))
bindMod("CTRL + mouse_up", hl.dsp.window.move({ workspace = "e-1", follow = false }))
bindMod("Tab", hl.dsp.focus({ workspace = "previous" }))

-- Named-workspace shortcuts matching Niri: stash, notes, AI.
for key, workspace in pairs({ s = 1, n = 4, a = 3 }) do
    bindMod(key, hl.dsp.focus({ workspace = workspace }))
    bindMod("CTRL + " .. key, hl.dsp.window.move({ workspace = workspace, follow = false }))
end
for workspace = 1, 9 do
    bindMod(tostring(workspace), hl.dsp.focus({ workspace = workspace }))
    bindMod("CTRL + " .. workspace, hl.dsp.window.move({ workspace = workspace, follow = false }))
end

-- Native approximation for Niri pin/stash: Hyprland special workspace.
bindMod("p", hl.dsp.workspace.toggle_special("stash"))
bindMod("o", hl.dsp.workspace.toggle_special("stash"))
bindMod("SHIFT + p", hl.dsp.window.move({ workspace = "special:stash", follow = false }))
-- TODO: direct equivalent for summon pinned window / move beside pinned.

-- Layout / state. Maximize/fullscreen are layout-handled, so the window stays a
-- column you can scroll away from and back to.
-- Maximized internally and to the client, so apps do not switch to their own fullscreen UI.
local toggleMaximizedColumn = hl.dsp.window.fullscreen_state({ internal = 1, client = 1, action = "toggle" })
bindMod("f", toggleMaximizedColumn)
bindMod("m", toggleMaximizedColumn)
bindMod("SHIFT + f", hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle" }))
bindMod("CTRL + f", layoutMessage("colresize 1.0"))
bindMod("minus", layoutMessage("colresize -0.1"))
bindMod("equal", layoutMessage("colresize +0.1"))
bindMod("Backspace", layoutMessage("colresize 0.5"))
bindMod("SHIFT + minus", layoutMessage("colresize all 0.333"))
bindMod("SHIFT + equal", layoutMessage("colresize all 0.667"))
bindMod("z", hl.dsp.window.float({ action = "toggle" }))
bindMod("bracketleft", layoutMessage("promote"))
bindMod("bracketright", layoutMessage("swapcol r"))
bindMod("t", hl.dsp.group.toggle())
bindMod("SHIFT + t", hl.dsp.group.next())

-- Scrolling mode: quick repeated controls for Hyprland's native scrolling layout.
bindMod("r", hl.dsp.submap("scroll"))
hl.define_submap("scroll", function()
    local repeating = { repeating = true }
    hl.bind("h", layoutMessage("move -col"), repeating)
    hl.bind("l", layoutMessage("move +col"), repeating)
    hl.bind("left", layoutMessage("move -col"), repeating)
    hl.bind("right", layoutMessage("move +col"), repeating)
    hl.bind("j", hl.dsp.focus({ direction = "down" }), repeating)
    hl.bind("k", hl.dsp.focus({ direction = "up" }), repeating)
    hl.bind("down", hl.dsp.focus({ direction = "down" }), repeating)
    hl.bind("up", hl.dsp.focus({ direction = "up" }), repeating)
    hl.bind("comma", layoutMessage("swapcol l"), repeating)
    hl.bind("period", layoutMessage("swapcol r"), repeating)
    hl.bind("minus", layoutMessage("colresize -0.1"), repeating)
    hl.bind("equal", layoutMessage("colresize +0.1"), repeating)
    hl.bind("Backspace", layoutMessage("colresize 0.5"))
    hl.bind("f", layoutMessage("fit active"))
    hl.bind("a", layoutMessage("fit all"))
    hl.bind("v", layoutMessage("fit visible"))
    hl.bind("Return", hl.dsp.submap("reset"))
    hl.bind("Escape", hl.dsp.submap("reset"))
end)

-- Emergency escape for stuck submaps.
bindMod("CTRL + Escape", hl.dsp.submap("reset"), { submap_universal = true })

-- Mouse bindings.
bindMod("mouse:272", hl.dsp.window.drag(), { mouse = true })
bindMod("mouse:273", hl.dsp.window.resize(), { mouse = true })

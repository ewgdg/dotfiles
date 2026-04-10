# Vim Mode
#
# ohmyzsh vi mode options
# VI_MODE_RESET_PROMPT_ON_MODE_CHANGE=false
# VI_MODE_SET_CURSOR=true
# MODE_INDICATOR=""
# INSERT_MODE_INDICATOR=""
# VI_MODE_CURSOR_NORMAL=1
# VI_MODE_CURSOR_VISUAL=1
# VI_MODE_CURSOR_INSERT=5
# VI_MODE_CURSOR_OPPEND=0

# zsh vi mode
bindkey -v
bindkey -M viins '^L' redisplay
bindkey -M vicmd '^L' redisplay

# change cursor
_fix_cursor() {
    local keymap=${1:-$KEYMAP}
    local shape=0
    case ${keymap} in
        vicmd|visual) shape=1 ;; # block
        viins|main|command|isearch) shape=5 ;; # beam
        viopp) shape=0 ;; # block
        *) shape=0 ;; # block
    esac
    printf $'\e[%d q' "${shape}"
}

__cursor_keymap_select() {
    _fix_cursor "${KEYMAP}"
}

__cursor_line_init() {
    _fix_cursor "${KEYMAP}"
}

__cursor_line_finish() {
    _fix_cursor vicmd
}

autoload -Uz add-zle-hook-widget

if (( ${+widgets[zle-keymap-select]} )); then
    add-zle-hook-widget keymap-select __cursor_keymap_select
else
    zle -N zle-keymap-select __cursor_keymap_select
fi

if (( ${+widgets[zle-line-init]} )); then
    add-zle-hook-widget line-init __cursor_line_init
else
    zle -N zle-line-init __cursor_line_init
fi

if (( ${+widgets[zle-line-finish]} )); then
    add-zle-hook-widget line-finish __cursor_line_finish
else
    zle -N zle-line-finish __cursor_line_finish
fi

autoload -Uz edit-command-line
zle -N edit-command-line
zle -A edit-command-line __cursor_edit_command_line_orig
__cursor_edit_command_line() {
    zle __cursor_edit_command_line_orig "$@"
    local ret=$?
    _fix_cursor "${KEYMAP:-viins}"
    return ${ret}
}
zle -N edit-command-line __cursor_edit_command_line

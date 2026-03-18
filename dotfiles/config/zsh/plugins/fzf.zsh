# fzf
# fzf, use fd instead of find (fd reads ~/.fdignore)
# Always wrap: bat wraps to preview width; fzf preview pane also wraps as backup.
if ! _ensure_command fzf "fzf shell integration"; then
    return 0
fi

local _fzf_dir_preview_command
if _ensure_command eza "directory previews"; then
    _fzf_dir_preview_command="eza -a --tree -L1 --color=always --icons=always {} | head -n 200"
else
    _fzf_dir_preview_command="ls -la {} | head -n 200"
fi

local _fzf_file_preview_command
if _ensure_command bat "file previews"; then
    _fzf_file_preview_command="bat --color=always --wrap=auto --terminal-width=\${FZF_PREVIEW_COLUMNS:-\${COLUMNS}} --line-range=:500 {}"
else
    _fzf_file_preview_command="sed -n '1,500p' {}"
fi

local _fzf_preview_argument="if [ -d {} ]; then ${_fzf_dir_preview_command}; else ${_fzf_file_preview_command}; fi"

if _ensure_command fd "fd-backed fzf defaults"; then
    export FZF_DEFAULT_COMMAND="fd -H -E .git --type d --type f"
    # Ctrl + T command
    export FZF_CTRL_T_COMMAND="${FZF_DEFAULT_COMMAND}"
    # Alt + C command 
    export FZF_ALT_C_COMMAND="fd -H -E .git --type d"

    # "**" command syntax
    _fzf_compgen_path() {
        fd -H -E .git --type d --type f . "$1"
    }
    # "**" command syntax (for directories only)
    _fzf_compgen_dir() {
        fd -H -E .git --type d . "$1"
    }
fi
export FZF_CTRL_T_OPTS="--bind 'ctrl-/:toggle-preview' ${FZF_CTRL_T_OPTS:-} --preview '${_fzf_preview_argument}' --preview-window wrap"
export FZF_ALT_C_OPTS="--bind 'ctrl-/:toggle-preview' ${FZF_ALT_C_OPTS:-} --preview '${_fzf_preview_argument}' --preview-window wrap"
# allow color from fd and set sane preview defaults globally
export FZF_DEFAULT_OPTS="--ansi ${FZF_DEFAULT_OPTS:-}"
_fzf_comprun() {
    local command=$1
    shift

    case "$command" in
        export|unset) fzf --preview "eval 'echo \$'{}" "$@" ;;
        ssh) fzf --preview "dig {}" "$@" ;;
        *) fzf --preview "${_fzf_preview_argument}" --preview-window wrap "$@" ;;
    esac
}
alias fzfp="fzf --preview '${_fzf_preview_argument}' --preview-window wrap"

source <(fzf --zsh)

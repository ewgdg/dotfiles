# Theme
#
# if use ohmyzsh vi mode then this need to be placed after it to enable transient prompt
if [ "$TERM_PROGRAM" != "Apple_Terminal" ]; then
    if _ensure_command oh-my-posh "prompt theme"; then
        eval "$(oh-my-posh init zsh --config ${HOME}/.config/oh-my-posh/custom.omp.toml)"
    fi
fi

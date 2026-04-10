# fnm
if _ensure_command fnm "fnm integration"; then
    # eval "$(fnm env --use-on-cd --shell zsh)"
    # eval "$(fnm env --use-on-cd --version-file-strategy=recursive --shell zsh)"
    eval "$(fnm env --shell zsh)"
fi

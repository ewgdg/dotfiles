# fnm
# Project-local node versions only: fnm deliberately has no default alias here, so
# the multishell link dangles and node resolves to the system node. fnm use still
# repoints this shell's link for a project that needs a different version.
if _ensure_command fnm "fnm integration"; then
    # eval "$(fnm env --use-on-cd --shell zsh)"
    # eval "$(fnm env --use-on-cd --version-file-strategy=recursive --shell zsh)"
    eval "$(fnm env --shell zsh)"
fi

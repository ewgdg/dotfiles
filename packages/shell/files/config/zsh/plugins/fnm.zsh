# fnm
# Optional: fnm is installed only by the untracked fnm package, so its absence is
# expected and stays silent.
if (( ${+commands[fnm]} )); then
    eval "$(fnm env --shell zsh)"
    # fnm env links every new shell to the `default` alias, and fnm install creates
    # that alias from the first version installed, so new shells are pinned back
    # to the system node. fnm use still switches a project shell when needed.
    fnm use system --silent-if-unchanged
fi

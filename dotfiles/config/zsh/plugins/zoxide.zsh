# zoxide
# export _ZO_DATA_DIR=$HOME/.local/share
export _ZO_ECHO=1
export _ZO_EXCLUDE_DIRS="$HOME:**/.git:**/.git/**:**/node_modules/**:/tmp:/tmp/**:/var/tmp/**"
if [ -n "$TMPDIR" ]; then
    _ZO_EXCLUDE_DIRS="$_ZO_EXCLUDE_DIRS:$TMPDIR:$TMPDIR/**"
fi
# eval "$(zoxide init --cmd cd zsh)"
if _ensure_command zoxide "zoxide integration"; then
    eval "$(zoxide init --cmd z zsh)"
fi

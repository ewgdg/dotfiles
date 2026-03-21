# alias
# normally the zshrc is only loaded for interactive shell,
# but sometimes it is sourced manually so it is still worth
# to have the interactive shell check.
if [[ -o interactive ]]; then
  if _ensure_command eza "ls/tree aliases"; then
    alias ls='eza --icons=auto'
    alias tree='eza --icons=auto --tree'
  fi

  # alias grep='rg'

  # fd
  # see also fd ignore file in ~/.config/fd/ignore
  if _ensure_command fd "fd alias"; then
    alias fd='fd --hidden --exclude .git' #-p
  fi

  if _ensure_command zoxide "cd alias"; then
    alias cd='z'
  fi

fi

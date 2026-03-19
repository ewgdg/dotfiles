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

  # Avoid .npmrc for setting the prefix because it conflicts with nvm.
  # Only force the user-local prefix when the active npm is not from nvm.
  # If nvm is initialized and you want the system toolchain again, run:
  #   nvm use system
  function npm() {
    local npm_path nvm_root npm_prefix
    npm_path="$(whence -p npm 2>/dev/null)"
    nvm_root="$NVM_DIR"
    npm_prefix="$HOME/.local"

    if [[ -n "$npm_path" && ( -z "$nvm_root" || "$npm_path" != ${nvm_root}/* ) ]]; then
      command npm --prefix "$npm_prefix" "$@"
      return
    fi

    command npm "$@"
  }
fi

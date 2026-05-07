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

  cliamp() {
    _ensure_command op "cliamp YT Music secrets" || return
    _ensure_command cliamp "cliamp YT Music secrets" || return

    local client_id client_secret
    client_id="$(op read 'op://dev/google-oauth-thirdparty-apps/client_id')" || return
    client_secret="$(op read 'op://dev/google-oauth-thirdparty-apps/client_secret')" || return

    YTMUSIC_CLIENT_ID="$client_id" \
      YTMUSIC_CLIENT_SECRET="$client_secret" \
      command cliamp "$@"
  }

fi

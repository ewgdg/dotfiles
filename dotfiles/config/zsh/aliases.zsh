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

  # Only override the global prefix for mutating global commands when the
  # configured prefix is not writable. This avoids sudo for system npm while
  # leaving normal commands and user-managed toolchains alone.
  function npm() {
    local npm_arg npm_command current_prefix prefix_probe user_npmrc npm_prefix
    local is_global=0 has_explicit_prefix=0 expect_location_value=0
    npm_prefix="${XDG_DATA_HOME:-$HOME/.local/share}/npm"

    for npm_arg in "$@"; do
      if [[ "$expect_location_value" -eq 1 ]]; then
        [[ "$npm_arg" == "global" ]] && is_global=1
        expect_location_value=0
        continue
      fi

      case "$npm_arg" in
        -g|--global|--location=global)
          is_global=1
          ;;
        --prefix|--prefix=*)
          has_explicit_prefix=1
          ;;
        --location)
          expect_location_value=1
          ;;
        -*)
          ;;
        *)
          [[ -z "$npm_command" ]] && npm_command="$npm_arg"
          ;;
      esac
    done

    if [[ "$has_explicit_prefix" -eq 0 ]]; then
      if [[ -n "${NPM_CONFIG_PREFIX:-${npm_config_prefix:-}}" ]]; then
        has_explicit_prefix=1
      else
        user_npmrc="${NPM_CONFIG_USERCONFIG:-${npm_config_userconfig:-$HOME/.npmrc}}"
        if [[ -f "$user_npmrc" ]] && grep -Eq '^[[:space:]]*prefix[[:space:]]*=' "$user_npmrc"; then
          has_explicit_prefix=1
        fi
      fi
    fi

    if [[ "$has_explicit_prefix" -eq 0 && "$is_global" -eq 1 ]]; then
      case "$npm_command" in
        install|i|add|update|up|upgrade|udpate|uninstall|remove|rm|r|un|unlink|link|ln)
          current_prefix="$(command npm config get prefix 2>/dev/null)"
          if [[ -n "$current_prefix" ]]; then
            prefix_probe="$current_prefix"
            while [[ ! -e "$prefix_probe" && "$prefix_probe" != "/" ]]; do
              prefix_probe="${prefix_probe:h}"
            done

            if [[ ! -w "$prefix_probe" ]]; then
              command npm --prefix "$npm_prefix" "$@"
              return
            fi
          fi
          ;;
      esac
    fi

    command npm "$@"
  }
fi

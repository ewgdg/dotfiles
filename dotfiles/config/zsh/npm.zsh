# Keep system npm usable without sudo while leaving user-managed toolchains,
# such as fnm, alone.

_npm_has_explicit_prefix() {
  local npm_arg user_npmrc expect_prefix_value=0

  if [[ -n ${NPM_CONFIG_PREFIX:-${npm_config_prefix:-}} ]]; then
    return 0
  fi

  user_npmrc="${NPM_CONFIG_USERCONFIG:-${npm_config_userconfig:-$HOME/.npmrc}}"
  if [[ -f "$user_npmrc" ]] && command grep -Eq '^[[:space:]]*prefix[[:space:]]*=' "$user_npmrc"; then
    return 0
  fi

  for npm_arg in "$@"; do
    if [[ "$expect_prefix_value" -eq 1 ]]; then
      return 0
    fi

    case "$npm_arg" in
      --)
        break
        ;;
      --prefix|-C)
        expect_prefix_value=1
        ;;
      --prefix=*|-C*)
        return 0
        ;;
    esac
  done

  return 1
}

_npm_needs_fallback_prefix() {
  local current_prefix prefix_probe

  current_prefix="$(command npm config get prefix 2>/dev/null)"
  [[ -n "$current_prefix" ]] || return 1

  prefix_probe="$current_prefix"
  while [[ ! -e "$prefix_probe" && "$prefix_probe" != "/" ]]; do
    prefix_probe="${prefix_probe:h}"
  done

  [[ ! -w "$prefix_probe" ]]
}

npm() {
  local npm_prefix

  if _npm_has_explicit_prefix "$@" || ! _npm_needs_fallback_prefix; then
    command npm "$@"
    return
  fi

  npm_prefix="${XDG_DATA_HOME:-$HOME/.local/share}/npm"
  NPM_CONFIG_PREFIX="$npm_prefix" command npm "$@"
}
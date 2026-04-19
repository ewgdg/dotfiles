#!/usr/bin/env sh
set -eu

usage() {
  cat >&2 <<'EOF'
usage: check_core_env.sh

Guard dotman push on repo shell core env sentinel.

Passes when DOTFILES_ENV_CORE_SH_LOADED matches repo core env token.
Set DOTFILES_SKIP_CORE_ENV_GUARD=1 to bypass intentionally.
EOF
}

expected_sentinel='dotfiles:packages/shell/files/env.core.sh'

case "${1:-}" in
  "")
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage
    exit 2
    ;;
esac

if [ "$#" -ne 0 ]; then
  usage
  exit 2
fi

is_affirmative() {
  case "${1:-}" in
    1|y|Y|yes|YES|true|TRUE|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if [ "${DOTFILES_ENV_CORE_SH_LOADED:-}" = "$expected_sentinel" ]; then
  exit 0
fi

if is_affirmative "${DOTFILES_SKIP_CORE_ENV_GUARD:-}"; then
  exit 0
fi

printf '%s\n' 'repo core env not loaded in current shell.' >&2
printf '%s\n' 'Run `. ./activate.sh` then retry.' >&2
printf '%s\n' 'Or set `DOTFILES_SKIP_CORE_ENV_GUARD=1` to bypass this guard intentionally.' >&2
exit 100


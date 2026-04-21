#!/usr/bin/env sh
set -eu

usage() {
  cat >&2 <<'EOF'
usage: check_core_env.sh

Guard dotman push on repo shell core env token.

Passes when DOTFILES_ENV_CORE_SH_TOKEN matches current repo core env token.
Set DOTFILES_SKIP_CORE_ENV_GUARD=1 to bypass intentionally.
EOF
}

script_dir="$(
  cd -- "$(dirname -- "$0")" >/dev/null 2>&1
  pwd -P
)"
repo_root="$(
  cd -- "${script_dir}/.." >/dev/null 2>&1
  pwd -P
)"
repo_core_env_path="${repo_root}/packages/shell/files/env.core.sh"
repo_core_env_token_script="${repo_root}/packages/shell/scripts/core_env_token.sh"

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

if [ ! -r "${repo_core_env_path}" ]; then
  printf '%s\n' "missing core env: ${repo_core_env_path}" >&2
  exit 1
fi

if [ ! -r "${repo_core_env_token_script}" ]; then
  printf '%s\n' "missing core env token helper: ${repo_core_env_token_script}" >&2
  exit 1
fi

expected_token="$(sh "${repo_core_env_token_script}" print "${repo_core_env_path}")" || {
  printf '%s\n' 'failed to compute repo core env token' >&2
  exit 1
}

if [ "${DOTFILES_ENV_CORE_SH_TOKEN:-}" = "$expected_token" ]; then
  exit 0
fi

if is_affirmative "${DOTFILES_SKIP_CORE_ENV_GUARD:-}"; then
  exit 0
fi

printf '%s\n' 'repo core env not loaded or stale in current shell.' >&2
printf '%s\n' 'Run `. ./activate.sh` then retry.' >&2
printf '%s\n' 'Or set `DOTFILES_SKIP_CORE_ENV_GUARD=1` to bypass this guard intentionally.' >&2
exit 100


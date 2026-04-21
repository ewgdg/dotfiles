#!/usr/bin/env sh

if ! (return 0 2>/dev/null); then
  printf '%s\n' "activate.sh must be sourced: . ./activate.sh" >&2
  exit 1
fi

# Must not change caller shell options. This file is sourced into interactive
# shells, so `set -e`/`set -u` here would leak into user session and can make
# Ctrl-C in later commands exit the whole shell.

script_dir="$(
  cd -- "$(dirname -- "$0")" >/dev/null 2>&1
  pwd -P
)"
repo_root="${script_dir}"
repo_core_env_path="${repo_root}/packages/shell/files/env.core.sh"
repo_core_env_token_script="${repo_root}/packages/shell/scripts/core_env_token.sh"

if [ ! -r "${repo_core_env_path}" ]; then
  printf '%s\n' "missing core env: ${repo_core_env_path}" >&2
  return 1
fi

if [ ! -r "${repo_core_env_token_script}" ]; then
  printf '%s\n' "missing core env token helper: ${repo_core_env_token_script}" >&2
  return 1
fi

# Keep one user-facing activation entrypoint while reusing managed core env.
# shellcheck source=/dev/null
. "${repo_core_env_path}"

core_env_token="$(sh "${repo_core_env_token_script}" print "${repo_core_env_path}")" || {
  printf '%s\n' 'failed to compute repo core env token' >&2
  return 1
}

export DOTFILES_ENV_CORE_SH_TOKEN="${core_env_token}"

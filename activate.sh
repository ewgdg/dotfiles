#!/usr/bin/env sh
set -eu

if ! (return 0 2>/dev/null); then
  printf '%s\n' "activate.sh must be sourced: . ./activate.sh" >&2
  exit 1
fi

script_dir="$(
  cd -- "$(dirname -- "$0")" >/dev/null 2>&1
  pwd -P
)"
repo_root="${script_dir}"
repo_core_env_path="${repo_root}/packages/shell/files/env.core.sh"

if [ ! -r "${repo_core_env_path}" ]; then
  printf '%s\n' "missing core env: ${repo_core_env_path}" >&2
  return 1
fi

# Keep one user-facing activation entrypoint while reusing managed core env.
# shellcheck source=/dev/null
. "${repo_core_env_path}"

#!/bin/sh
# Global npm packages live in one shared prefix (see ~/.npmrc) and carry native
# bindings compiled for a single node ABI (NODE_MODULE_VERSION). Swapping the
# system node to another LTS line invalidates every one of them, so the ABI the
# tree was last rebuilt for is recorded and compared with the running node.
#
# The stamp records what the rebuild actually did rather than loading an installed
# module to see whether it works: a load test fails for reasons unrelated to the
# ABI, and a probe that never reports "current" would rebuild on every push.
set -eu

action="${1:-}"
case "${action}" in
  probe|apply) ;;
  *)
    echo "usage: npm_globals_abi.sh probe|apply" >&2
    exit 2
    ;;
esac

state_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/dotfiles/nodejs"
stamp="${state_dir}/npm-globals-abi"

# No usable node means the install target has not run yet; a rebuild here would
# only fail, so leave it alone.
current_abi="$(node -p 'process.versions.modules' 2>/dev/null || true)"
if [ -z "${current_abi}" ]; then
  echo "no usable node; leaving global npm packages alone" >&2
  exit 100
fi

recorded_abi="$(cat "${stamp}" 2>/dev/null || true)"

if [ "${recorded_abi}" = "${current_abi}" ]; then
  echo "global npm packages are built for node ABI ${current_abi}" >&2
  exit 100
fi

if [ "${action}" = "probe" ]; then
  echo "global npm packages are built for ABI ${recorded_abi:-unknown}, node is ${current_abi}" >&2
  exit 0
fi

npm rebuild -g

# Written only after a successful rebuild, so a failure retries on the next push
# instead of leaving the tree recorded as current.
mkdir -p "${state_dir}"
printf '%s\n' "${current_abi}" > "${stamp}"
echo "rebuilt global npm packages for node ABI ${current_abi}" >&2

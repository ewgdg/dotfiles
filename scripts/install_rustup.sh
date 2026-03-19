#!/usr/bin/env bash
set -euo pipefail

if command -v rustup >/dev/null 2>&1; then
  echo "rustup is already installed at $(command -v rustup); skipping installer."
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to install rustup." >&2
  exit 1
fi

installer_script_path="$(mktemp "${TMPDIR:-/tmp}/rustup-init.XXXXXX.sh")"
cleanup() {
  rm -f "${installer_script_path}"
}
trap cleanup EXIT

curl --proto '=https' -sSf https://sh.rustup.rs -o "${installer_script_path}"
sh "${installer_script_path}" -y --no-modify-path

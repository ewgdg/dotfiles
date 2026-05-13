#!/usr/bin/env bash
set -euo pipefail

rustup_command() {
  if command -v rustup >/dev/null 2>&1; then
    command -v rustup
    return 0
  fi

  if [ -x "$HOME/.cargo/bin/rustup" ]; then
    printf '%s\n' "$HOME/.cargo/bin/rustup"
    return 0
  fi

  return 1
}

install_rustup_with_upstream_installer() {
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
}

ensure_default_toolchain() {
  rustup_path="$(rustup_command)"

  if "$rustup_path" show active-toolchain >/dev/null 2>&1; then
    return 0
  fi

  echo "installing default stable Rust toolchain"
  "$rustup_path" default stable
}

if rustup_path="$(rustup_command)"; then
  echo "rustup is already installed at ${rustup_path}; skipping installer."
  ensure_default_toolchain
  exit 0
fi

install_rustup_with_upstream_installer

if ! rustup_command >/dev/null 2>&1; then
  echo "rustup not found after installation." >&2
  exit 1
fi

ensure_default_toolchain

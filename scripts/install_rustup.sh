#!/usr/bin/env bash
set -euo pipefail

required_rustup_components=(clippy rustfmt rust-src)
required_rustup_targets=()

if [ -n "${RUSTUP_EXTRA_TARGETS:-}" ]; then
  read -r -a required_rustup_targets <<<"$RUSTUP_EXTRA_TARGETS"
fi

pacman_available() {
  command -v pacman >/dev/null 2>&1
}

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

install_rustup_with_pacman() {
  if pacman -Q -- rustup >/dev/null 2>&1; then
    return 0
  fi

  if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    pacman -S --needed --noconfirm rustup
    return 0
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is required to install rustup with pacman." >&2
    exit 1
  fi

  sudo pacman -S --needed --noconfirm rustup
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

ensure_required_components() {
  rustup_path="$(rustup_command)"
  "$rustup_path" component add "${required_rustup_components[@]}"
}

ensure_required_targets() {
  if [ "${#required_rustup_targets[@]}" -eq 0 ]; then
    return 0
  fi

  rustup_path="$(rustup_command)"
  "$rustup_path" target add "${required_rustup_targets[@]}"
}

if pacman_available; then
  install_rustup_with_pacman

  if ! rustup_command >/dev/null 2>&1; then
    echo "rustup not found after Arch package installation." >&2
    exit 1
  fi

  ensure_default_toolchain
  ensure_required_components
  ensure_required_targets
  exit 0
fi

if rustup_path="$(rustup_command)"; then
  echo "rustup is already installed at ${rustup_path}; skipping installer."
  ensure_default_toolchain
  ensure_required_components
  ensure_required_targets
  exit 0
fi

install_rustup_with_upstream_installer

if ! rustup_command >/dev/null 2>&1; then
  echo "rustup not found after installation." >&2
  exit 1
fi

ensure_default_toolchain
ensure_required_components
ensure_required_targets

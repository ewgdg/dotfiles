#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <toolchain>" >&2
  exit 2
fi

toolchain_name="$1"
rustup_bin=""

if command -v rustup >/dev/null 2>&1; then
  rustup_bin="$(command -v rustup)"
elif command -v brew >/dev/null 2>&1; then
  # Homebrew installs rustup as a keg-only formula, so it may not be on PATH.
  brew_rustup_prefix="$(brew --prefix rustup 2>/dev/null || true)"
  if [[ -n "${brew_rustup_prefix}" && -x "${brew_rustup_prefix}/bin/rustup" ]]; then
    rustup_bin="${brew_rustup_prefix}/bin/rustup"
  fi
fi

if [[ -z "${rustup_bin}" ]]; then
  echo "Skipping rustup initialization: rustup is not available." >&2
  exit 0
fi

if active_toolchain="$("${rustup_bin}" show active-toolchain 2>/dev/null)" && [[ -n "${active_toolchain}" ]]; then
  echo "rustup is already initialized with ${active_toolchain}."
  exit 0
fi

"${rustup_bin}" default "${toolchain_name}"

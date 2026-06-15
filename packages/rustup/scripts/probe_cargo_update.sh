#!/usr/bin/env bash

set -euo pipefail

if ! command -v cargo >/dev/null 2>&1; then
    printf '%s\n' 'cargo is missing; cargo-update install needed' >&2
    exit 0
fi

if ! cargo install-update --version >/dev/null 2>&1; then
    printf '%s\n' 'cargo-update is missing; install needed' >&2
    exit 0
fi

printf '%s\n' 'cargo-update is installed' >&2
exit 100

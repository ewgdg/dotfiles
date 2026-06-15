#!/usr/bin/env bash

set -euo pipefail

required_components=(clippy rustfmt rust-src)

rustup_path=""
if command -v rustup >/dev/null 2>&1; then
    rustup_path=$(command -v rustup)
elif [ -x "$HOME/.cargo/bin/rustup" ]; then
    rustup_path=$HOME/.cargo/bin/rustup
fi

if [ -z "$rustup_path" ]; then
    printf '%s\n' 'rustup is missing; install needed' >&2
    exit 0
fi

if ! "$rustup_path" show active-toolchain >/dev/null 2>&1; then
    printf '%s\n' 'rustup has no active toolchain; setup needed' >&2
    exit 0
fi

installed_components=$("$rustup_path" component list --installed 2>/dev/null || true)
for component in "${required_components[@]}"; do
    if ! printf '%s\n' "$installed_components" | grep -Eq "^${component}($|-)"; then
        printf 'rustup component missing: %s\n' "$component" >&2
        exit 0
    fi
done

printf '%s\n' 'rustup toolchain state is ready' >&2
exit 100

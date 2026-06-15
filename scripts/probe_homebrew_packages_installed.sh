#!/bin/sh

set -eu

if [ "$#" -eq 0 ]; then
    printf 'usage: %s <package>...\n' "${0##*/}" >&2
    exit 64
fi

if ! command -v brew >/dev/null 2>&1; then
    printf '%s\n' 'error: brew is required to probe Homebrew package state' >&2
    exit 127
fi

missing_packages=""
for package_name do
    if ! brew list --versions "$package_name" >/dev/null 2>&1; then
        missing_packages="${missing_packages}${missing_packages:+ }$package_name"
    fi
done

if [ -z "$missing_packages" ]; then
    printf 'Homebrew packages already installed: %s\n' "$*" >&2
    exit 100
fi

printf 'missing Homebrew packages: %s\n' "$missing_packages" >&2
exit 0

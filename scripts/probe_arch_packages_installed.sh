#!/bin/sh

set -eu

if [ "$#" -eq 0 ]; then
    printf 'usage: %s <package>...\n' "${0##*/}" >&2
    exit 64
fi

if ! command -v pacman >/dev/null 2>&1; then
    printf '%s\n' 'error: pacman is required to probe Arch package state' >&2
    exit 127
fi

missing_packages=""
for package_name do
    if ! pacman -Q -- "$package_name" >/dev/null 2>&1; then
        missing_packages="${missing_packages}${missing_packages:+ }$package_name"
    fi
done

if [ -z "$missing_packages" ]; then
    printf 'Arch packages already installed: %s\n' "$*" >&2
    exit 100
fi

printf 'missing Arch packages: %s\n' "$missing_packages" >&2
exit 0

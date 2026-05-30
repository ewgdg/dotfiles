#!/bin/sh

set -eu

missing_packages=""

for package_name do
    if ! pacman -Q -- "$package_name" >/dev/null 2>&1; then
        missing_packages="${missing_packages}${missing_packages:+ }$package_name"
    fi
done

[ -n "$missing_packages" ] || exit 0

if ! command -v paru >/dev/null 2>&1; then
    script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    sh "$script_dir/install_paru.sh"
fi

if ! command -v paru >/dev/null 2>&1; then
    printf 'error: paru is required to install Arch packages: %s\n' "$missing_packages" >&2
    exit 127
fi

printf '%s\n' "$missing_packages" | xargs -r paru -S --needed --noconfirm --skipreview --useask

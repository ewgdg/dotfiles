#!/bin/sh

set -eu

missing_packages=""

for package_name do
    if ! pacman -Q -- "$package_name" >/dev/null 2>&1; then
        missing_packages="${missing_packages}${missing_packages:+ }$package_name"
    fi
done

[ -n "$missing_packages" ] || exit 0

printf '%s\n' "$missing_packages" | xargs -r yay -S --needed --answerdiff=None --answeredit=None

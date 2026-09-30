#!/bin/sh

# Usage: latest_appimage_url.sh <cpu-arch>
#
# Prints the download URL of the latest AppImage for <cpu-arch> (dotman's
# `cpu_arch`, i.e. `uname -m`). Release assets carry the version in their name
# and upstream publishes no unversioned alias, so read it from the
# electron-updater manifest, the same file the app updates from.

set -eu

release_base=https://github.com/pingdotgg/t3code/releases/latest/download

# electron-builder names arm64 builds `arm64` and gives them their own manifest.
case "${1:?usage: latest_appimage_url.sh <cpu-arch>}" in
x86_64)
    manifest=latest-linux.yml
    asset_arch=x86_64
    ;;
aarch64 | arm64)
    manifest=latest-linux-arm64.yml
    asset_arch=arm64
    ;;
*)
    printf 'error: no T3 Code AppImage for CPU architecture %s\n' "$1" >&2
    exit 1
    ;;
esac

appimage_file=$(
    curl -fsSL --retry 3 "$release_base/$manifest" |
        sed -n "s/^  - url: \(T3-Code-.*-$asset_arch\.AppImage\)\$/\1/p"
)
if [ -z "$appimage_file" ]; then
    printf 'error: no %s AppImage listed in %s/%s\n' "$asset_arch" "$release_base" "$manifest" >&2
    exit 1
fi

printf '%s/%s\n' "$release_base" "$appimage_file"

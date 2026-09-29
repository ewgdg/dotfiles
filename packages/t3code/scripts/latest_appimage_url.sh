#!/bin/sh

# Prints the download URL of the latest x86_64 AppImage. Release assets carry
# the version in their name and upstream publishes no unversioned alias, so read
# it from the electron-updater manifest, the same file the app updates from.

set -eu

release_base=https://github.com/pingdotgg/t3code/releases/latest/download

appimage_file=$(
    curl -fsSL --retry 3 "$release_base/latest-linux.yml" |
        sed -n 's/^  - url: \(T3-Code-.*-x86_64\.AppImage\)$/\1/p'
)
if [ -z "$appimage_file" ]; then
    printf 'error: no x86_64 AppImage listed in %s/latest-linux.yml\n' "$release_base" >&2
    exit 1
fi

printf '%s/%s\n' "$release_base" "$appimage_file"

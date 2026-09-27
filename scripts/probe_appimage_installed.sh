#!/bin/sh

set -eu

usage() {
    printf 'usage: %s [--link-command] <name>\n' "${0##*/}" >&2
    exit 64
}

link_command=false
if [ "${1:-}" = --link-command ]; then
    link_command=true
    shift
fi
[ "$#" -eq 1 ] || usage

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_dir/appimage_paths.sh"
set_appimage_paths "$1"

missing=""
[ -x "$appimage_path" ] || missing="$missing AppImage"
find_desktop_entry >/dev/null || missing="$missing desktop-entry"
if [ "$link_command" = true ] && [ "$(readlink -- "$command_path" || true)" != "$appimage_path" ]; then
    missing="$missing command-link"
fi

if [ -z "$missing" ]; then
    printf 'AppImage already installed: %s\n' "$appimage_path" >&2
    exit 100
fi

printf 'AppImage %s missing:%s\n' "$1" "$missing" >&2
exit 0

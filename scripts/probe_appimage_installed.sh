#!/bin/sh

set -eu

usage() {
    printf 'usage: %s --name <name> [--link-command]\n' "${0##*/}" >&2
    exit 64
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_dir/appimage_paths.sh"
parse_appimage_args "$@"
[ -z "$url" ] || usage
set_appimage_paths

desktop_entry=""
[ ! -f "$record_path" ] || desktop_entry=$(head -n 1 "$record_path")

missing=""
[ -x "$appimage_path" ] || missing="$missing AppImage"
{ [ -n "$desktop_entry" ] && [ -f "$desktop_entry" ]; } || missing="$missing desktop-entry"
if [ "$link_command" = true ] && [ "$(readlink -- "$command_path" || true)" != "$appimage_path" ]; then
    missing="$missing command-link"
fi

if [ -z "$missing" ]; then
    printf 'AppImage already installed: %s\n' "$appimage_path" >&2
    exit 100
fi

printf 'AppImage %s missing:%s\n' "$name" "$missing" >&2
exit 0

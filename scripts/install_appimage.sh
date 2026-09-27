#!/bin/sh

# Installs an AppImage that updates itself at ~/Applications/<name>.AppImage and
# adds its desktop entry and icons. Only the first download is ours: afterwards
# the app replaces that file in place, so an existing AppImage is never
# re-downloaded, only re-integrated.

set -eu

usage() {
    printf 'usage: %s [--link-command] <name> <url>\n' "${0##*/}" >&2
    exit 64
}

link_command=false
if [ "${1:-}" = --link-command ]; then
    link_command=true
    shift
fi
[ "$#" -eq 2 ] || usage
name=$1
url=$2

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_dir/appimage_paths.sh"
set_appimage_paths "$name"

download_appimage() {
    mkdir -p "$appimage_dir"
    curl -fL --retry 3 -o "$appimage_path.part" "$url"
    chmod 755 "$appimage_path.part"
    mv "$appimage_path.part" "$appimage_path"
}

# Extracts only metadata; the runtime handles --appimage-extract before the
# app starts, so this works for apps that treat arguments as CLI commands.
extract_metadata() {
    (
        cd "$extract_dir"
        "$appimage_path" --appimage-extract '*.desktop' >/dev/null
        "$appimage_path" --appimage-extract 'usr/share/icons/*' >/dev/null
    )
}

install_desktop_entry() {
    source_entry=$(find "$extract_dir/squashfs-root" -maxdepth 1 -name '*.desktop')
    if [ "$(printf '%s\n' "$source_entry" | grep -c .)" -ne 1 ]; then
        printf 'error: expected one top-level desktop entry in %s\n' "$appimage_path" >&2
        exit 65
    fi

    # Drop entries written for this AppImage earlier, so an upstream rename of
    # its desktop file does not leave a duplicate launcher behind.
    find_desktop_entry | while IFS= read -r previous_entry; do
        rm -f -- "$previous_entry"
    done

    # Point Exec at the stable AppImage path, keeping upstream arguments.
    mkdir -p "$applications_dir"
    sed \
        -e "s|^Exec=[^ ]*|Exec=\"$appimage_path\"|" \
        -e "s|^TryExec=.*|TryExec=$appimage_path|" \
        "$source_entry" >"$applications_dir/${source_entry##*/}"

    icon_name=$(sed -n 's/^Icon=//p' "$source_entry" | head -n 1)
}

install_icons() {
    icon_root=$extract_dir/squashfs-root/usr/share/icons
    icon_files=""
    if [ -n "$icon_name" ] && [ -d "$icon_root" ]; then
        icon_files=$(cd "$icon_root" && find . -path "*/apps/$icon_name.*")
    fi
    # Only hicolor-style icon trees are supported; electron-builder always ships one.
    if [ -z "$icon_files" ]; then
        printf 'error: no usr/share/icons/*/apps/%s.* in %s\n' "$icon_name" "$appimage_path" >&2
        exit 65
    fi
    (cd "$icon_root" && printf '%s\n' "$icon_files" | xargs cp -L --parents -t "$icons_dir")
}

[ -x "$appimage_path" ] || download_appimage

extract_dir=$(mktemp -d)
trap 'rm -rf "$extract_dir"' EXIT
extract_metadata
install_desktop_entry
mkdir -p "$icons_dir"
install_icons

# Registers MimeType handlers such as x-scheme-handler links.
update-desktop-database "$applications_dir"

if [ "$link_command" = true ]; then
    mkdir -p "$command_dir"
    ln -sfn "$appimage_path" "$command_path"
fi

printf 'AppImage installed: %s\n' "$appimage_path" >&2

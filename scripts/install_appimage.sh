#!/bin/sh

# Installs an AppImage that updates itself at ~/Applications/<name>.AppImage and
# adds its desktop entry and icons. Only the first download is ours: afterwards
# the app replaces that file in place, so an existing AppImage is never
# re-downloaded, only re-integrated.

set -eu

usage() {
    printf 'usage: %s --name <name> --url <url> [--link-command] [--drop-mime-types]\n' "${0##*/}" >&2
    exit 64
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_dir/appimage_paths.sh"
parse_appimage_args "$@"
[ -n "$url" ] || usage
set_appimage_paths

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

# Sets $source_entry and $icon_files (relative to $icon_root), failing before
# anything installed is touched.
locate_metadata() {
    source_entry=$(find "$extract_dir/squashfs-root" -maxdepth 1 -name '*.desktop')
    if [ "$(printf '%s\n' "$source_entry" | grep -c .)" -ne 1 ]; then
        printf 'error: expected one top-level desktop entry in %s\n' "$appimage_path" >&2
        exit 65
    fi

    icon_name=$(sed -n 's/^Icon=//p' "$source_entry" | head -n 1)
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
}

# Removes what the previous integration recorded, so an upstream rename of the
# desktop entry or icon leaves nothing stale behind.
remove_recorded_files() {
    [ -f "$record_path" ] || return 0
    while IFS= read -r recorded_file; do
        rm -f -- "$recorded_file"
    done <"$record_path"
}

install_desktop_entry() {
    desktop_entry=$applications_dir/${source_entry##*/}
    # Apps that register their own hidden URL-handler entry at runtime would
    # otherwise appear twice in "Open with" choosers for their schemes.
    drop_mime_types_script=
    [ "$drop_mime_types" = false ] || drop_mime_types_script='/^MimeType=/d'
    # Point Exec at the stable AppImage path, keeping upstream arguments.
    mkdir -p "$applications_dir"
    sed \
        -e "s|^Exec=[^ ]*|Exec=\"$appimage_path\"|" \
        -e "s|^TryExec=.*|TryExec=$appimage_path|" \
        -e "$drop_mime_types_script" \
        "$source_entry" >"$desktop_entry"
    printf '%s\n' "$desktop_entry" >>"$record_path.part"
}

install_icons() {
    mkdir -p "$icons_dir"
    (cd "$icon_root" && printf '%s\n' "$icon_files" | xargs cp -L --parents -t "$icons_dir")
    printf '%s\n' "$icon_files" | sed "s|^\./|$icons_dir/|" >>"$record_path.part"
}

[ -x "$appimage_path" ] || download_appimage

extract_dir=$(mktemp -d)
trap 'rm -rf "$extract_dir"' EXIT
extract_metadata
locate_metadata

mkdir -p "$record_dir"
: >"$record_path.part"
remove_recorded_files
install_desktop_entry
install_icons
mv "$record_path.part" "$record_path"

# Registers MimeType handlers such as x-scheme-handler links.
update-desktop-database "$applications_dir"

if [ "$link_command" = true ]; then
    mkdir -p "$command_dir"
    ln -sfn "$appimage_path" "$command_path"
fi

printf 'AppImage installed: %s\n' "$appimage_path" >&2

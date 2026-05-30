#!/bin/sh

set -eu

keep_src=false
case "${1:-}" in
    --keepsrc)
        keep_src=true
        shift
        ;;
esac

if [ "$#" -ne 1 ]; then
    printf 'usage: %s [--keepsrc] <pkgbuild-dir>\n' "$0" >&2
    exit 64
fi

pkgbuild_dir=$1
case "$pkgbuild_dir" in
    /*) ;;
    *)
        if [ -n "${DOTMAN_REPO_ROOT:-}" ]; then
            pkgbuild_dir=$DOTMAN_REPO_ROOT/$pkgbuild_dir
        fi
        ;;
esac

if ! command -v paru >/dev/null 2>&1; then
    printf 'error: paru is required to build/install custom Arch PKGBUILD: %s\n' "$pkgbuild_dir" >&2
    exit 127
fi

if [ ! -f "$pkgbuild_dir/PKGBUILD" ]; then
    printf 'error: PKGBUILD not found in %s\n' "$pkgbuild_dir" >&2
    exit 66
fi

cache_root=${XDG_CACHE_HOME:-"$HOME/.cache"}/makepkg/local
pkgbuild_cache_parent="$cache_root/pkgbuilds"

# paru/makepkg writes build artifacts into its build input. Never point it at
# the dotfiles working tree; copy the PKGBUILD directory into cache first.
pkgbuild_name=$(basename "$pkgbuild_dir")
pkgbuild_build_dir="$pkgbuild_cache_parent/$pkgbuild_name"
build_dest="$cache_root/builds"
source_dest="$cache_root/sources/$pkgbuild_name"
package_dest="$cache_root/packages"
source_package_dest="$cache_root/source-packages"
log_dest="$cache_root/logs/$pkgbuild_name"

mkdir -p \
    "$pkgbuild_cache_parent" \
    "$pkgbuild_build_dir" \
    "$build_dest" \
    "$source_dest" \
    "$package_dest" \
    "$source_package_dest" \
    "$log_dest"

export BUILDDIR="$build_dest"
export SRCDEST="$source_dest"
export PKGDEST="$package_dest"
export SRCPKGDEST="$source_package_dest"
export LOGDEST="$log_dest"
if command -v rsync >/dev/null 2>&1; then
    # Mirror tracked PKGBUILD inputs into staging; mutable makepkg state lives in
    # BUILDDIR/SRCDEST/PKGDEST/LOGDEST/SRCPKGDEST outside this tree.
    set -- -a --delete
    if [ -f "$pkgbuild_dir/.gitignore" ]; then
        set -- "$@" "--exclude-from=$pkgbuild_dir/.gitignore"
    fi
    set -- "$@" \
        --exclude='/.git/' \
        --exclude='/src/' \
        --exclude='/pkg/' \
        --exclude='/*.pkg.tar*' \
        "$pkgbuild_dir/" \
        "$pkgbuild_build_dir/"
    rsync "$@"
else
    printf '%s\n' "warning: rsync not found; staging with cp -a, stale removed files may remain in $pkgbuild_build_dir" >&2
    cp -a "$pkgbuild_dir/." "$pkgbuild_build_dir/"
fi

set -- -Bi --needed --noconfirm --skipreview --useask "$pkgbuild_build_dir"

if [ "$keep_src" = true ]; then
    set -- --keepsrc "$@"
fi

exec paru "$@"

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

mkdir -p "$pkgbuild_cache_parent"

# paru/makepkg writes build artifacts into its build input. Never point it at
# the dotfiles working tree; copy the PKGBUILD directory into cache first.
pkgbuild_name=$(basename "$pkgbuild_dir")
pkgbuild_build_dir="$pkgbuild_cache_parent/$pkgbuild_name"
mkdir -p "$pkgbuild_build_dir"
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude='/.git/' \
        --exclude='/src/' \
        --exclude='/pkg/' \
        --exclude='/*.pkg.tar*' \
        "$pkgbuild_dir/" \
        "$pkgbuild_build_dir/"
else
    printf '%s\n' "warning: rsync not found; staging with cp -a, stale removed files may remain in $pkgbuild_build_dir" >&2
    cp -a "$pkgbuild_dir/." "$pkgbuild_build_dir/"
fi

set -- -Bi --needed --noconfirm --skipreview --useask "$pkgbuild_build_dir"

if [ "$keep_src" = true ]; then
    set -- --keepsrc "$@"
fi

exec paru "$@"

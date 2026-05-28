#!/bin/sh

set -eu

if [ "$#" -ne 1 ]; then
    printf 'usage: %s <pkgbuild-dir>\n' "$0" >&2
    exit 64
fi

pkgbuild_dir=$1

if ! command -v yay >/dev/null 2>&1; then
    printf 'error: yay is required to build/install local Arch PKGBUILD: %s\n' "$pkgbuild_dir" >&2
    exit 127
fi

if [ ! -f "$pkgbuild_dir/PKGBUILD" ]; then
    printf 'error: PKGBUILD not found in %s\n' "$pkgbuild_dir" >&2
    exit 66
fi

cache_root=${XDG_CACHE_HOME:-"$HOME/.cache"}/makepkg/local

mkdir -p \
    "$cache_root/sources" \
    "$cache_root/packages" \
    "$cache_root/build"

export SRCDEST="$cache_root/sources"
export PKGDEST="$cache_root/packages"
export BUILDDIR="$cache_root/build"

exec yay -Bi --needed --noconfirm --useask --answerclean=None --answerdiff=None --answeredit=None --answerupgrade=None "$pkgbuild_dir"

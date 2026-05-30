#!/bin/sh

set -eu

paru_aur_package=${PARU_AUR_PACKAGE:-paru-bin}
aur_git_url=${PARU_AUR_GIT_URL:-"https://aur.archlinux.org/${paru_aur_package}.git"}
cache_root=${XDG_CACHE_HOME:-"$HOME/.cache"}/makepkg/aur-bootstrap
src_dir=${PARU_AUR_SOURCE_DIR:-"$cache_root/$paru_aur_package"}

if command -v paru >/dev/null 2>&1; then
    exit 0
fi

if ! command -v pacman >/dev/null 2>&1; then
    printf '%s\n' "error: pacman is required to bootstrap paru on Arch Linux." >&2
    exit 127
fi

if [ "$(id -u)" -eq 0 ]; then
    printf '%s\n' "error: run this script as a regular user; makepkg refuses to run as root." >&2
    exit 77
fi

install_bootstrap_dependencies() {
    if command -v sudo >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm base-devel git
        return 0
    fi

    printf '%s\n' "error: sudo is required to install paru bootstrap dependencies: base-devel git" >&2
    exit 1
}

install_bootstrap_dependencies

if ! command -v git >/dev/null 2>&1; then
    printf '%s\n' "error: git not found after installing bootstrap dependencies." >&2
    exit 127
fi

if ! command -v makepkg >/dev/null 2>&1; then
    printf '%s\n' "error: makepkg not found after installing bootstrap dependencies." >&2
    exit 127
fi

mkdir -p "$(dirname "$src_dir")"

if [ -d "$src_dir/.git" ]; then
    git -C "$src_dir" pull --ff-only
elif [ -e "$src_dir" ]; then
    printf 'error: paru source path exists but is not a git checkout: %s\n' "$src_dir" >&2
    exit 73
else
    git clone "$aur_git_url" "$src_dir"
fi

(
    cd "$src_dir"
    makepkg -si --needed --noconfirm
)

if ! command -v paru >/dev/null 2>&1; then
    printf '%s\n' "error: paru not found after AUR bootstrap." >&2
    exit 1
fi

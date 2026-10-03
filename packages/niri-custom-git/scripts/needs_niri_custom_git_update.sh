#!/usr/bin/env bash

set -euo pipefail

usage() {
    printf 'usage: %s <pkgbuild-dir>\n' "${0##*/}" >&2
}

if [ "$#" -ne 1 ]; then
    usage
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

pkgbuild_path=$pkgbuild_dir/PKGBUILD
if [ ! -f "$pkgbuild_path" ]; then
    printf 'error: PKGBUILD not found: %s\n' "$pkgbuild_path" >&2
    exit 66
fi

if ! command -v pacman >/dev/null 2>&1; then
    printf 'error: pacman is required to probe niri-custom-git installation state\n' >&2
    exit 127
fi
if ! command -v git >/dev/null 2>&1; then
    printf 'error: git is required to probe niri-custom-git upstream state\n' >&2
    exit 127
fi

# Trusted repo-owned PKGBUILD is source of truth for pkgname and upstream git URL.
# shellcheck source=/dev/null
source "$pkgbuild_path"

package_name=${pkgname:?PKGBUILD must set pkgname}
git_url=""
for source_entry in "${source[@]}"; do
    source_entry=${source_entry#*::}
    case "$source_entry" in
        git+*)
            git_url=${source_entry#git+}
            break
            ;;
    esac
done

if [ -z "$git_url" ]; then
    printf 'error: no git source found in %s\n' "$pkgbuild_path" >&2
    exit 65
fi

installed_record=$(pacman -Q "$package_name" 2>/dev/null || true)
if [ -z "$installed_record" ]; then
    printf '%s is not installed; install needed\n' "$package_name" >&2
    exit 0
fi

installed_package_version=${installed_record#"$package_name "}
installed_pkgver=${installed_package_version%-*}
installed_commit=$(printf '%s\n' "$installed_pkgver" | sed -n 's/.*\.g\([0-9a-fA-F][0-9a-fA-F]*\)$/\1/p')
if [ -z "$installed_commit" ]; then
    printf '%s has no git hash in installed version %s; rebuild needed\n' "$package_name" "$installed_package_version" >&2
    exit 0
fi

remote_commit=$(git ls-remote "$git_url" HEAD | awk 'NR == 1 { print $1 }')
if [ -z "$remote_commit" ]; then
    printf 'error: failed to read upstream HEAD from %s\n' "$git_url" >&2
    exit 69
fi

case "$remote_commit" in
    "$installed_commit"*)
        printf '%s is current at %s\n' "$package_name" "$installed_commit" >&2
        exit 100
        ;;
esac

compare_url=""
case "$git_url" in
    https://github.com/*/*.git|https://github.com/*/*)
        github_path=${git_url#https://github.com/}
        github_path=${github_path%.git}
        compare_url="https://api.github.com/repos/$github_path/compare/$installed_commit...$remote_commit"
        ;;
esac

compare_status=""
if [ -n "$compare_url" ] && command -v python3 >/dev/null 2>&1; then
    compare_status=$(
        python3 - "$compare_url" <<'PY' 2>/dev/null || true
import json
import sys
from urllib.request import Request, urlopen

request = Request(sys.argv[1], headers={"Accept": "application/vnd.github+json"})
with urlopen(request, timeout=20) as response:
    print(json.load(response).get("status", ""))
PY
    )
fi

case "$compare_status" in
    identical|behind)
        printf '%s is current enough: installed %s, upstream %s (%s)\n' \
            "$package_name" "$installed_commit" "$remote_commit" "$compare_status" >&2
        exit 100
        ;;
    ahead)
        printf '%s update available: installed %s, upstream %s\n' \
            "$package_name" "$installed_commit" "$remote_commit" >&2
        exit 0
        ;;
    diverged)
        printf '%s upstream diverged from installed %s to %s; rebuild needed\n' \
            "$package_name" "$installed_commit" "$remote_commit" >&2
        exit 0
        ;;
esac

printf '%s upstream HEAD differs from installed %s to %s; rebuild needed\n' \
    "$package_name" "$installed_commit" "$remote_commit" >&2
exit 0

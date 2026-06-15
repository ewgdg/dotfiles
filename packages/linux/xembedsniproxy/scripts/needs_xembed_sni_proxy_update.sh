#!/usr/bin/env bash

set -euo pipefail

git_url=${1:-}
package_name=${2:-xembed-sni-proxy}

if [ -z "$git_url" ]; then
    printf 'usage: %s <git-url> [package-name]\n' "${0##*/}" >&2
    exit 64
fi

if ! command -v cargo >/dev/null 2>&1; then
    printf '%s\n' 'cargo is missing; install needed' >&2
    exit 0
fi
if ! command -v git >/dev/null 2>&1; then
    printf '%s\n' 'git is missing; install needed' >&2
    exit 0
fi

installed_line=$(cargo install --list 2>/dev/null | awk -v package_name="$package_name" '$1 == package_name { print; exit }')
if [ -z "$installed_line" ]; then
    printf '%s is not installed; install needed\n' "$package_name" >&2
    exit 0
fi

installed_commit=$(printf '%s\n' "$installed_line" | sed -n 's/.*#\([0-9a-fA-F][0-9a-fA-F]*\)).*/\1/p')
if [ -z "$installed_commit" ]; then
    printf '%s has no git hash in cargo install metadata; reinstall needed\n' "$package_name" >&2
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

printf '%s update available: installed %s, upstream %s\n' \
    "$package_name" "$installed_commit" "$remote_commit" >&2
exit 0

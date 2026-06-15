#!/usr/bin/env bash

set -euo pipefail

package_name=surf-cli

if ! command -v surf >/dev/null 2>&1; then
    printf '%s\n' 'surf is missing; install needed' >&2
    exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
    printf '%s\n' 'npm is missing; surf-cli install needed' >&2
    exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'python3 is missing; cannot inspect npm package metadata' >&2
    exit 127
fi

installed_version=$(npm list -g "$package_name" --depth=0 --json 2>/dev/null \
    | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("dependencies",{}).get("surf-cli",{}).get("version", ""))' 2>/dev/null || true)
if [ -z "$installed_version" ]; then
    printf '%s\n' 'surf-cli npm metadata missing; reinstall needed' >&2
    exit 0
fi

latest_version=$(npm view "$package_name" version --silent 2>/dev/null || true)
if [ -z "$latest_version" ]; then
    printf '%s\n' 'warning: could not determine latest surf-cli version; keeping installed copy' >&2
    exit 100
fi

if [ "$installed_version" = "$latest_version" ]; then
    printf 'surf-cli is current at %s\n' "$installed_version" >&2
    exit 100
fi

printf 'surf-cli update available: installed %s, latest %s\n' "$installed_version" "$latest_version" >&2
exit 0

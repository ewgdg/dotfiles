#!/usr/bin/env bash

set -euo pipefail

module_path=github.com/tomasz-tomczyk/crit

crit_path=$(command -v crit 2>/dev/null || true)
if [ -z "$crit_path" ]; then
    printf '%s\n' 'crit is missing; install needed' >&2
    exit 0
fi

if ! command -v go >/dev/null 2>&1; then
    printf '%s\n' 'go is missing; crit install needed' >&2
    exit 0
fi

installed_version=$(go version -m "$crit_path" 2>/dev/null | awk -v module_path="$module_path" '$1 == "mod" && $2 == module_path { print $3; exit }')
if [ -z "$installed_version" ]; then
    printf '%s\n' 'crit version metadata missing; reinstall needed' >&2
    exit 0
fi

latest_version=$(go list -m -f '{{.Version}}' "$module_path@latest" 2>/dev/null || true)
if [ -z "$latest_version" ]; then
    printf '%s\n' 'warning: could not determine latest crit version; keeping installed copy' >&2
    exit 100
fi

if [ "$installed_version" = "$latest_version" ]; then
    printf 'crit is current at %s\n' "$installed_version" >&2
    exit 100
fi

printf 'crit update available: installed %s, latest %s\n' "$installed_version" "$latest_version" >&2
exit 0

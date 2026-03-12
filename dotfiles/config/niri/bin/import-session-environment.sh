#!/bin/sh

set -eu

env_file="${1:-${XDG_CONFIG_HOME:-$HOME/.config}/niri/session.env}"

if [ ! -f "$env_file" ]; then
    printf 'import-session-environment: env file not found: %s\n' "$env_file" >&2
    exit 1
fi

variables="$(
    awk -F= '
        /^[[:space:]]*#/ || /^[[:space:]]*$/ {
            next;
        }
        /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/ {
            name = $1;
            sub(/^[[:space:]]+/, "", name);
            sub(/[[:space:]]+$/, "", name);
            printf "%s ", name;
        }
    ' "$env_file"
)"

if [ -z "$variables" ]; then
    printf 'import-session-environment: no environment variables found in %s\n' "$env_file" >&2
    exit 1
fi

set -a
. "$env_file"
set +a

if command -v dbus-update-activation-environment >/dev/null 2>&1; then
    dbus-update-activation-environment --systemd $variables
else
    systemctl --user import-environment $variables
fi

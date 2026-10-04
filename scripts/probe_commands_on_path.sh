#!/bin/sh

set -eu

if [ "$#" -eq 0 ]; then
    printf 'usage: %s <command>...\n' "${0##*/}" >&2
    exit 64
fi

missing_commands=""
for command_name do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        missing_commands="${missing_commands}${missing_commands:+ }$command_name"
    fi
done

if [ -z "$missing_commands" ]; then
    exit 100
fi

printf 'missing commands on PATH: %s\n' "$missing_commands" >&2
exit 0

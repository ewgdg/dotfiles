#!/bin/sh

set -eu

if [ "$#" -lt 2 ]; then
    printf 'usage: %s [--same-workspace] <app-id-regex> <command> [args...]\n' "$0" >&2
    exit 2
fi

same_workspace=0
if [ "${1:-}" = "--same-workspace" ]; then
    same_workspace=1
    shift
fi

if [ "$#" -lt 2 ]; then
    printf 'usage: %s [--same-workspace] <app-id-regex> <command> [args...]\n' "$0" >&2
    exit 2
fi

app_id_pattern="$1"
shift

focused_app_id="$(
    niri msg -j focused-window 2>/dev/null \
        | jq -r '.app_id // empty'
)"

focused_workspace_id=
if [ "$same_workspace" -eq 1 ]; then
    focused_workspace_id="$(
        niri msg -j workspaces 2>/dev/null \
            | jq -r '.[] | select(.is_focused) | .id // empty'
    )"
fi

if printf '%s' "$focused_app_id" | jq -Rre --arg pattern "$app_id_pattern" 'test($pattern)' >/dev/null; then
    exec "$@"
fi

window_id="$(
    niri msg -j windows \
        | jq -r --arg pattern "$app_id_pattern" --argjson workspace_id "${focused_workspace_id:-null}" '
            map(select(.app_id | test($pattern)))
            | map(select($workspace_id == null or .workspace_id == $workspace_id))
            | sort_by(.focus_timestamp.secs, .focus_timestamp.nanos)
            | last
            | .id // empty
        '
)"

if [ -n "$window_id" ]; then
    exec niri msg action focus-window --id "$window_id"
fi

exec "$@"

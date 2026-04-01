#!/bin/sh

set -eu

if [ "$#" -lt 2 ]; then
    printf 'usage: %s [--same-workspace] [--switch-back-if-focused] [--no-relaunch-when-focused] <app-id-regex> <command> [args...]\n' "$0" >&2
    exit 2
fi

same_workspace=0
switch_back_if_focused=0
no_relaunch_when_focused=0

while [ "$#" -gt 0 ]; do
    case "${1:-}" in
        --same-workspace)
            same_workspace=1
            shift
            ;;
        --switch-back-if-focused)
            switch_back_if_focused=1
            shift
            ;;
        --no-relaunch-when-focused)
            no_relaunch_when_focused=1
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            printf 'usage: %s [--same-workspace] [--switch-back-if-focused] [--no-relaunch-when-focused] <app-id-regex> <command> [args...]\n' "$0" >&2
            exit 2
            ;;
        *)
            break
            ;;
    esac
done

if [ "$#" -lt 2 ]; then
    printf 'usage: %s [--same-workspace] [--switch-back-if-focused] [--no-relaunch-when-focused] <app-id-regex> <command> [args...]\n' "$0" >&2
    exit 2
fi

app_id_pattern="$1"
shift

focused_window_json="$(
    niri msg -j focused-window 2>/dev/null || printf '{}'
)"
focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"
focused_app_id="$(
    printf '%s' "$focused_window_json" \
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
    if [ "$switch_back_if_focused" -eq 1 ]; then
        exec niri msg action focus-window-previous
    fi

    if [ "$no_relaunch_when_focused" -eq 1 ]; then
        if [ -n "$focused_window_id" ]; then
            exec niri msg action focus-window --id "$focused_window_id"
        fi

        exit 0
    fi

    exec "$@"
fi

window_id="$(
    niri msg -j windows \
        | jq -r --arg pattern "$app_id_pattern" --argjson workspace_id "${focused_workspace_id:-null}" '
            map(select((.app_id // "") | test($pattern)))
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

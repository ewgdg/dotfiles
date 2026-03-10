#!/bin/sh

set -eu

usage() {
    printf 'usage: %s [--float] [--hide|--hide-to-scratchpad] <app-id-regex> <command> [args...]\n' "$0" >&2
    exit 2
}

if [ "$#" -lt 2 ]; then
    usage
fi

float_window=false
hide_to_scratchpad=false

while [ "$#" -gt 0 ]; do
    case "${1:-}" in
        --float)
            float_window=true
            shift
            ;;
        --hide|--hide-to-scratchpad)
            hide_to_scratchpad=true
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            usage
            ;;
        *)
            break
            ;;
    esac
done

if [ "$#" -lt 2 ]; then
    usage
fi

app_id_pattern="$1"
shift

hide_focused_window() {
    if [ "$hide_to_scratchpad" = "true" ]; then
        exec niri msg action move-window-to-workspace --focus false scratchpad
    fi

    exec niri msg action close-window
}

focused_window_json="$(
    niri msg -j focused-window 2>/dev/null || printf '{}'
)"
focused_app_id="$(printf '%s' "$focused_window_json" | jq -r '.app_id // empty')"

if printf '%s' "$focused_app_id" | jq -Rre --arg pattern "$app_id_pattern" 'test($pattern)' >/dev/null; then
    hide_focused_window
fi

focused_workspace_ref="$(
    niri msg -j workspaces 2>/dev/null \
        | jq -r '
            .[]
            | select(.is_focused)
            | if (.name // "") != "" then .name else (.idx | tostring) end
        '
)"

matching_windows_json() {
    niri msg -j windows 2>/dev/null \
        | jq -c --arg pattern "$app_id_pattern" '
            map(select((.app_id // "") | test($pattern)))
            | sort_by(.focus_timestamp.secs, .focus_timestamp.nanos)
        '
}

target_window_id() {
    printf '%s' "$1" | jq -r 'last | .id // empty'
}

target_is_floating() {
    printf '%s' "$1" | jq -r --argjson target_id "$2" '
        .[]
        | select(.id == $target_id)
        | .is_floating // false
    '
}

close_extra_windows() {
    printf '%s' "$1" \
        | jq -r --argjson target_id "$2" '.[] | select(.id != $target_id) | .id' \
        | while IFS= read -r window_id; do
            [ -n "$window_id" ] || continue
            niri msg action close-window --id "$window_id"
        done
}

matching_json="$(matching_windows_json)"
target_id="$(target_window_id "$matching_json")"

if [ -z "$target_id" ]; then
    "$@" >/dev/null 2>&1 &

    attempts=50
    while [ "$attempts" -gt 0 ]; do
        matching_json="$(matching_windows_json)"
        target_id="$(target_window_id "$matching_json")"
        if [ -n "$target_id" ]; then
            break
        fi
        attempts=$((attempts - 1))
        sleep 0.1
    done

    if [ -z "$target_id" ]; then
        printf 'failed to find a matching window for pattern %s after spawning\n' "$app_id_pattern" >&2
        exit 1
    fi
else
    close_extra_windows "$matching_json" "$target_id"
fi

niri msg action move-window-to-workspace --window-id "$target_id" --focus false "$focused_workspace_ref"
niri msg action focus-window --id "$target_id"

target_floating="$(target_is_floating "$(matching_windows_json)" "$target_id")"
if [ "$float_window" = "true" ] && [ "$target_floating" != "true" ]; then
    niri msg action move-window-to-floating --id "$target_id"
fi

if [ "$float_window" = "true" ]; then
    exec niri msg action center-window --id "$target_id"
fi

exit 0

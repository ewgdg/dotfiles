#!/bin/sh

set -eu

usage() {
    printf 'usage: %s <status-json|summon|toggle|clear>\n' "$0" >&2
    exit 2
}

runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
state_file="$runtime_dir/niri-pinned-window.json"
fallback_workspace="main"

if [ "$#" -ne 1 ]; then
    usage
fi

mkdir -p "$runtime_dir"

write_state_json() {
    temp_file="$(mktemp "$runtime_dir/niri-pinned-window.XXXXXX")"
    printf '%s\n' "$1" >"$temp_file"
    mv "$temp_file" "$state_file"
}

write_unpinned_state() {
    write_state_json '{"pinned":false,"id":""}'
}

read_state_json() {
    if [ ! -r "$state_file" ]; then
        return 1
    fi

    state_json="$(cat "$state_file")"
    if [ -z "$state_json" ]; then
        return 1
    fi

    if ! printf '%s' "$state_json" | jq -e . >/dev/null 2>&1; then
        return 1
    fi

    printf '%s\n' "$state_json"
}

read_pinned_window_id() {
    state_json="$(read_state_json || true)"
    if [ -z "$state_json" ]; then
        return 1
    fi

    pinned_window_id="$(
        printf '%s' "$state_json" \
            | jq -r 'if (.pinned // false) then (.id // "") else "" end'
    )"
    if [ -z "$pinned_window_id" ]; then
        return 1
    fi

    printf '%s\n' "$pinned_window_id"
}

write_pinned_window_id() {
    write_state_json "{\"pinned\":true,\"id\":\"$1\"}"
}

clear_pinned_window_id() {
    write_unpinned_state
}

window_exists() {
    niri msg -j windows 2>/dev/null \
        | jq -e --arg target_window_id "$1" '
            any(.[]; (.id | tostring) == $target_window_id)
        ' >/dev/null
}

print_status_json() {
    pinned_window_id="$(read_pinned_window_id || true)"
    if [ -z "$pinned_window_id" ]; then
        write_unpinned_state
        printf '%s\n' '{"pinned":false,"id":""}'
        exit 0
    fi

    windows_json="$(niri msg -j windows 2>/dev/null || printf '[]')"
    window_json="$(
        printf '%s' "$windows_json" \
            | jq -c --arg target_window_id "$pinned_window_id" '
                map(select((.id | tostring) == $target_window_id))
                | first
            '
    )"

    if [ "$window_json" = "null" ] || [ -z "$window_json" ]; then
        clear_pinned_window_id
        printf '%s\n' '{"pinned":false,"id":""}'
        exit 0
    fi

    printf '%s' "$window_json" \
        | jq -c '
            {
                pinned: true,
                id: (.id | tostring),
                app_id: (.app_id // ""),
                title: (.title // ""),
                is_focused: (.is_focused // false),
                is_floating: (.is_floating // false),
                workspace_name: (.workspace_name // ""),
                workspace_id: (.workspace_id // null)
            }
        '
}

summon_pinned_window() {
    pinned_window_id="$(read_pinned_window_id || true)"
    if [ -z "$pinned_window_id" ]; then
        exec niri msg action focus-workspace "$fallback_workspace"
    fi

    if ! window_exists "$pinned_window_id"; then
        clear_pinned_window_id
        exec niri msg action focus-workspace "$fallback_workspace"
    fi

    focused_window_json="$(niri msg -j focused-window 2>/dev/null || printf '{}')"
    focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"
    if [ "$focused_window_id" = "$pinned_window_id" ]; then
        exec niri msg action focus-window-previous
    fi

    exec niri msg action focus-window --id "$pinned_window_id"
}

toggle_pinned_window() {
    focused_window_json="$(niri msg -j focused-window 2>/dev/null || printf '{}')"
    focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"

    if [ -z "$focused_window_id" ]; then
        printf '%s: no focused window to pin\n' "$0" >&2
        exit 1
    fi

    current_pinned_window_id="$(read_pinned_window_id || true)"
    if [ "$current_pinned_window_id" = "$focused_window_id" ]; then
        clear_pinned_window_id
        exit 0
    fi

    write_pinned_window_id "$focused_window_id"
}

case "$1" in
    status-json)
        print_status_json
        ;;
    summon)
        summon_pinned_window
        ;;
    toggle)
        toggle_pinned_window
        ;;
    clear)
        clear_pinned_window_id
        ;;
    *)
        usage
        ;;
esac

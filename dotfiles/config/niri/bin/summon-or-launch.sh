#!/bin/sh

set -eu

usage() {
    printf 'usage: %s [--same-workspace] [--relaunch-if-focused] [--singleton] [--float] [--hide|--hide-to-stash] <app-id-regex> <command> [args...]\n' "$0" >&2
    exit 2
}

same_workspace=0
relaunch_if_focused=0
singleton_mode=0
float_window=0
hide_to_stash=0

while [ "$#" -gt 0 ]; do
    case "${1:-}" in
        --same-workspace)
            same_workspace=1
            shift
            ;;
        --relaunch-if-focused)
            relaunch_if_focused=1
            shift
            ;;
        --singleton)
            singleton_mode=1
            shift
            ;;
        --float)
            float_window=1
            shift
            ;;
        --hide|--hide-to-stash)
            hide_to_stash=1
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

[ "$#" -ge 2 ] || usage

app_id_pattern="$1"
shift

focused_window_json="$(
    niri msg -j focused-window 2>/dev/null || printf '{}'
)"
focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"
focused_app_id="$(printf '%s' "$focused_window_json" | jq -r '.app_id // empty')"
focused_window_workspace_id="$(printf '%s' "$focused_window_json" | jq -r '.workspace_id // empty')"
focused_workspace_id=""

if [ "$same_workspace" -eq 1 ]; then
    focused_workspace_id="$(
        niri msg -j workspaces 2>/dev/null \
            | jq -r '.[] | select(.is_focused) | .id // empty'
    )"
fi

focused_workspace_ref="$(
    niri msg -j workspaces 2>/dev/null \
        | jq -r '
            .[]
            | select(.is_focused)
            | if (.name // "") != "" then .name else (.idx | tostring) end
        '
)"

previous_focused_window_on_current_workspace() {
    target_focused_window_id="$1"
    target_workspace_id="$2"

    [ -n "$target_focused_window_id" ] || return 1
    [ -n "$target_workspace_id" ] || return 1

    niri msg -j windows 2>/dev/null \
        | jq -e \
            --argjson target_focused_window_id "$target_focused_window_id" \
            --argjson target_workspace_id "$target_workspace_id" '
                (
                    map(select(.id != $target_focused_window_id))
                    | sort_by(.focus_timestamp.secs // 0, .focus_timestamp.nanos // 0)
                    | last
                    | .workspace_id?
                ) == $target_workspace_id
            ' >/dev/null
}

dismiss_focused_window() {
    if previous_focused_window_on_current_workspace "$focused_window_id" "$focused_window_workspace_id"; then
        # Keep summon placement anchored near the previous window when toggling.
        niri msg action focus-window-previous >/dev/null 2>&1 || true
    fi

    if [ "$hide_to_stash" -eq 1 ]; then
        exec niri msg action move-window-to-workspace --window-id "$focused_window_id" --focus false stash
    fi

    exec niri msg action close-window --id "$focused_window_id"
}

matching_windows_json() {
    if [ "$same_workspace" -eq 1 ]; then
        [ -n "$focused_workspace_id" ] || {
            printf '[]'
            return 0
        }

        niri msg -j windows 2>/dev/null \
            | jq -c --arg pattern "$app_id_pattern" --argjson workspace_id "$focused_workspace_id" '
                map(select((.app_id // "") | test($pattern)))
                | map(select(.workspace_id == $workspace_id))
                | sort_by(.focus_timestamp.secs // 0, .focus_timestamp.nanos // 0)
            '
        return 0
    fi

    niri msg -j windows 2>/dev/null \
        | jq -c --arg pattern "$app_id_pattern" '
            map(select((.app_id // "") | test($pattern)))
            | sort_by(.focus_timestamp.secs // 0, .focus_timestamp.nanos // 0)
        '
}

target_window_id() {
    printf '%s' "$1" | jq -r 'last | .id // empty'
}

close_extra_windows() {
    printf '%s' "$1" \
        | jq -r --argjson target_id "$2" '.[] | select(.id != $target_id) | .id' \
        | while IFS= read -r window_id; do
            [ -n "$window_id" ] || continue
            niri msg action close-window --id "$window_id"
        done
}

summon_window() {
    target_window_id="$1"

    set -- --place-near-focused-window "$target_window_id"

    if [ "$float_window" -eq 1 ]; then
        set -- --float "$@"
    fi

    if [ "$singleton_mode" -eq 1 ] && [ -n "$focused_workspace_ref" ]; then
        set -- --workspace "$focused_workspace_ref" "$@"
    fi

    exec "$HOME/.config/niri/bin/summon-window.sh" "$@"
}

matching_json="$(matching_windows_json)"

if printf '%s' "$focused_app_id" | jq -Rre --arg pattern "$app_id_pattern" 'test($pattern)' >/dev/null; then
    if [ "$singleton_mode" -eq 1 ]; then
        dismiss_focused_window
    fi

    if [ "$relaunch_if_focused" -eq 1 ]; then
        exec "$@"
    fi

    exit 0
fi

window_id="$(target_window_id "$matching_json")"

if [ -n "$window_id" ]; then
    if [ "$singleton_mode" -eq 1 ]; then
        close_extra_windows "$matching_json" "$window_id"
    fi

    summon_window "$window_id"
fi

if [ "$singleton_mode" -eq 0 ]; then
    exec "$@"
fi

# New singleton windows need a real Niri window id before they can be placed
# near the current focus or floated/centered via summon-window.sh.
"$@" >/dev/null 2>&1 &

attempts=50
while [ "$attempts" -gt 0 ]; do
    matching_json="$(matching_windows_json)"
    window_id="$(target_window_id "$matching_json")"
    if [ -n "$window_id" ]; then
        summon_window "$window_id"
    fi

    attempts=$((attempts - 1))
    sleep 0.1
done

printf 'failed to find a matching window for pattern %s after spawning\n' "$app_id_pattern" >&2
exit 1

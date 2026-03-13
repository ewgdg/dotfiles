#!/bin/sh

set -eu

usage() {
    printf 'usage: %s [--workspace <workspace-ref>] [--place-near-focused-window] [--place-after-window <window-id>] [--move-tiled-column] [--float] [--center] <window-id>\n' "$0" >&2
    exit 2
}

target_workspace_ref=""
place_near_focused_window=false
place_after_window_id=""
move_tiled_column=false
float_window=false
center_window=false

while [ "$#" -gt 0 ]; do
    case "${1:-}" in
        --workspace)
            [ "$#" -ge 2 ] || usage
            target_workspace_ref="$2"
            shift 2
            ;;
        --place-near-focused-window)
            place_near_focused_window=true
            shift
            ;;
        --place-after-window)
            [ "$#" -ge 2 ] || usage
            place_after_window_id="$2"
            shift 2
            ;;
        --move-tiled-column)
            move_tiled_column=true
            shift
            ;;
        --float)
            float_window=true
            shift
            ;;
        --center)
            center_window=true
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

[ "$#" -eq 1 ] || usage

target_window_id="$1"

target_window_json="$(
    niri msg -j windows 2>/dev/null \
        | jq -c --argjson target_window_id "$target_window_id" '
            .[]
            | select(.id == $target_window_id)
        '
)"

if [ -z "$target_window_json" ]; then
    printf 'failed to find window id %s\n' "$target_window_id" >&2
    exit 1
fi

if [ -z "$target_workspace_ref" ]; then
    target_workspace_ref="$(
        niri msg -j workspaces 2>/dev/null \
            | jq -r '
                .[]
                | select(.is_focused)
                | if (.name // "") != "" then .name else (.idx | tostring) end
            '
    )"
fi

if [ -z "$target_workspace_ref" ]; then
    printf 'failed to detect the target workspace\n' >&2
    exit 1
fi

focused_window_json="$(
    niri msg -j focused-window 2>/dev/null || printf '{}'
)"
focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"
focused_window_column_index="$(printf '%s' "$focused_window_json" | jq -r '.layout.pos_in_scrolling_layout[0] // empty')"
target_is_floating="$(printf '%s' "$target_window_json" | jq -r '.is_floating // false')"
placement_column_index=""

if [ -z "$place_after_window_id" ] && [ "$place_near_focused_window" = "true" ]; then
    place_after_window_id="$focused_window_id"
fi

if [ -n "$place_after_window_id" ] && [ "$target_window_id" != "$place_after_window_id" ]; then
    if [ "$place_after_window_id" = "$focused_window_id" ]; then
        placement_reference_window_json="$focused_window_json"
    else
        placement_reference_window_json="$(
            niri msg -j windows 2>/dev/null \
                | jq -c --arg target_window_id "$place_after_window_id" '
                    .[]
                    | select((.id | tostring) == $target_window_id)
                '
        )"
    fi

    if [ -n "${placement_reference_window_json:-}" ] && [ "$(printf '%s' "$placement_reference_window_json" | jq -r --arg target_workspace_ref "$target_workspace_ref" '
        if (.workspace_name // "") == $target_workspace_ref then
            "true"
        elif .workspace_id != null and ((.workspace_id | tostring) == $target_workspace_ref) then
            "true"
        else
            "false"
        end
    ')" = "true" ]; then
        placement_column_index="$(printf '%s' "$placement_reference_window_json" | jq -r '.layout.pos_in_scrolling_layout[0] // empty')"
    fi
fi

if [ "$move_tiled_column" = "true" ] && [ "$target_is_floating" != "true" ]; then
    if [ "$focused_window_id" != "$target_window_id" ]; then
        niri msg action focus-window --id "$target_window_id"
    fi
    niri msg action move-column-to-workspace --focus false "$target_workspace_ref"
else
    niri msg action move-window-to-workspace --window-id "$target_window_id" --focus false "$target_workspace_ref"
fi

if [ -n "$placement_column_index" ] && [ "$target_is_floating" != "true" ]; then
    niri msg action focus-window --id "$target_window_id"
    niri msg action move-column-to-index $((placement_column_index + 1))
fi

if [ "$float_window" = "true" ] && [ "$target_is_floating" != "true" ]; then
    niri msg action move-window-to-floating --id "$target_window_id"
    target_is_floating=true
fi

if [ "$center_window" = "true" ] || [ "$float_window" = "true" ]; then
    exec niri msg action center-window --id "$target_window_id"
fi

exec niri msg action focus-window --id "$target_window_id"

exit 0

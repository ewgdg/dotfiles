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

target_workspace_id="$(
    niri msg -j workspaces 2>/dev/null \
        | jq -r --arg workspace_ref "$target_workspace_ref" '
            (
                map(select((.name // "") == $workspace_ref)) | first
            ) // (
                map(select((.idx | tostring) == $workspace_ref)) | first
            ) // empty
            | .id // empty
        '
)"

focused_window_json="$(
    niri msg -j focused-window 2>/dev/null || printf '{}'
)"
focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"
target_window_column_index="$(printf '%s' "$target_window_json" | jq -r '.layout.pos_in_scrolling_layout[0] // empty')"
target_window_workspace_id="$(printf '%s' "$target_window_json" | jq -r '.workspace_id // empty')"
target_is_floating="$(printf '%s' "$target_window_json" | jq -r '.is_floating // false')"
placement_column_index=""
column_repositioned=0
anchor_window_id=""

if [ "$place_near_focused_window" = "true" ] && [ -n "$focused_window_id" ] && [ "$focused_window_id" != "$target_window_id" ]; then
    # Re-focus the original anchor just before the final summon focus so Niri
    # keeps the viewport anchored around the caller, not around the moved window.
    anchor_window_id="$focused_window_id"
fi

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

    placement_reference_on_target_workspace=false
    if [ -n "${placement_reference_window_json:-}" ] && [ -n "$target_workspace_id" ]; then
        placement_reference_on_target_workspace="$(
            printf '%s' "$placement_reference_window_json" \
                | jq -r --argjson target_workspace_id "$target_workspace_id" '
                    if .workspace_id == $target_workspace_id then
                        "true"
                    else
                        "false"
                    end
                '
        )"
    fi

    if [ "$placement_reference_on_target_workspace" = "true" ]; then
        placement_column_index="$(printf '%s' "$placement_reference_window_json" | jq -r '.layout.pos_in_scrolling_layout[0] // empty')"

    fi
fi

if [ "$move_tiled_column" = "true" ] && [ "$target_is_floating" != "true" ]; then
    if [ "$focused_window_id" != "$target_window_id" ]; then
        niri msg action focus-window --id "$target_window_id"
    fi
    niri msg action move-column-to-workspace --focus false "$target_workspace_ref"
elif [ "$target_is_floating" != "true" ] \
    && [ -n "$target_workspace_id" ] \
    && [ "$target_window_workspace_id" = "$target_workspace_id" ]; then
    # Reorder an existing tiled column directly on the same workspace. The
    # workspace move path does not preserve the viewport anchor reliably here.
    if [ "$focused_window_id" != "$target_window_id" ]; then
        niri msg action focus-window --id "$target_window_id"
    fi

    if [ -n "$placement_column_index" ] && [ -n "$target_window_column_index" ]; then
        # move-column-to-index inserts before the destination index. Adjust the
        # target slot so the summoned column ends up just to the right of anchor.
        target_column_destination_index=$((placement_column_index + 1))

        if [ "$target_window_column_index" -lt "$placement_column_index" ]; then
            target_column_destination_index=$placement_column_index
        fi

        niri msg action move-column-to-index "$target_column_destination_index"
        column_repositioned=1
    fi
else
    niri msg action move-window-to-workspace --window-id "$target_window_id" --focus false "$target_workspace_ref"
fi

if [ "$column_repositioned" -eq 0 ] && [ -n "$placement_column_index" ] && [ "$target_is_floating" != "true" ]; then
    niri msg action focus-window --id "$target_window_id"
    niri msg action move-column-to-index $((placement_column_index + 1))
fi

if [ "$float_window" = "true" ] && [ "$target_is_floating" != "true" ]; then
    niri msg action move-window-to-floating --id "$target_window_id"
    target_is_floating=true
fi

if [ "$center_window" = "true" ] || [ "$float_window" = "true" ]; then
    niri msg action center-window --id "$target_window_id"
fi

if [ -n "$anchor_window_id" ]; then
    niri msg action focus-window --id "$anchor_window_id"
fi

exec niri msg action focus-window --id "$target_window_id"

exit 0

#!/bin/sh

set -eu

scratchpad_workspace_name="scratchpad"

focused_workspace_ref="$(
    niri msg -j workspaces 2>/dev/null \
        | jq -r --arg scratchpad_workspace_name "$scratchpad_workspace_name" '
            .[]
            | select(.is_focused)
            | if (.name // "") != "" then .name else (.idx | tostring) end
        '
)"

if [ -z "$focused_workspace_ref" ]; then
    printf 'failed to detect the focused workspace\n' >&2
    exit 1
fi

if [ "$focused_workspace_ref" = "$scratchpad_workspace_name" ]; then
    niri msg action focus-workspace-previous >/dev/null 2>&1 || true
    focused_workspace_ref="$(
        niri msg -j workspaces 2>/dev/null \
            | jq -r --arg scratchpad_workspace_name "$scratchpad_workspace_name" '
                .[]
                | select(.is_focused and ((.name // "") != $scratchpad_workspace_name))
                | if (.name // "") != "" then .name else (.idx | tostring) end
            '
    )"
fi

if [ -z "$focused_workspace_ref" ] || [ "$focused_workspace_ref" = "$scratchpad_workspace_name" ]; then
    printf 'failed to find a non-scratchpad target workspace\n' >&2
    exit 1
fi

scratchpad_workspace_id="$(
    niri msg -j workspaces 2>/dev/null \
        | jq -r --arg scratchpad_workspace_name "$scratchpad_workspace_name" '
            .[]
            | select((.name // "") == $scratchpad_workspace_name)
            | .id // empty
        '
)"

if [ -z "$scratchpad_workspace_id" ]; then
    printf 'failed to find the scratchpad workspace id\n' >&2
    exit 1
fi

scratchpad_window_json="$(
    niri msg -j windows 2>/dev/null \
        | jq -c --argjson scratchpad_workspace_id "$scratchpad_workspace_id" '
            map(select(.workspace_id == $scratchpad_workspace_id))
            | sort_by(.focus_timestamp.secs, .focus_timestamp.nanos)
            | last // empty
        '
)"

scratchpad_window_id="$(printf '%s' "$scratchpad_window_json" | jq -r '.id // empty')"

if [ -z "$scratchpad_window_id" ]; then
    exit 0
fi

exec "$HOME/.config/niri/bin/summon-window.sh" --workspace "$focused_workspace_ref" --place-near-focused-window "$scratchpad_window_id"

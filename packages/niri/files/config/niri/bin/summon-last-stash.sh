#!/bin/sh

set -eu

stash_workspace_name="stash"

focused_workspace_ref="$(
    niri msg -j workspaces 2>/dev/null \
        | jq -r --arg stash_workspace_name "$stash_workspace_name" '
            .[]
            | select(.is_focused)
            | if (.name // "") != "" then .name else (.idx | tostring) end
        '
)"

if [ -z "$focused_workspace_ref" ]; then
    printf 'failed to detect the focused workspace\n' >&2
    exit 1
fi

if [ "$focused_workspace_ref" = "$stash_workspace_name" ]; then
    niri msg action focus-workspace-previous >/dev/null 2>&1 || true
    focused_workspace_ref="$(
        niri msg -j workspaces 2>/dev/null \
            | jq -r --arg stash_workspace_name "$stash_workspace_name" '
                .[]
                | select(.is_focused and ((.name // "") != $stash_workspace_name))
                | if (.name // "") != "" then .name else (.idx | tostring) end
            '
    )"
fi

if [ -z "$focused_workspace_ref" ] || [ "$focused_workspace_ref" = "$stash_workspace_name" ]; then
    printf 'failed to find a non-stash target workspace\n' >&2
    exit 1
fi

stash_workspace_id="$(
    niri msg -j workspaces 2>/dev/null \
        | jq -r --arg stash_workspace_name "$stash_workspace_name" '
            .[]
            | select((.name // "") == $stash_workspace_name)
            | .id // empty
        '
)"

if [ -z "$stash_workspace_id" ]; then
    printf 'failed to find the stash workspace id\n' >&2
    exit 1
fi

stash_window_json="$(
    niri msg -j windows 2>/dev/null \
        | jq -c --argjson stash_workspace_id "$stash_workspace_id" '
            map(select(.workspace_id == $stash_workspace_id))
            | sort_by(.focus_timestamp.secs, .focus_timestamp.nanos)
            | last // empty
        '
)"

stash_window_id="$(printf '%s' "$stash_window_json" | jq -r '.id // empty')"

if [ -z "$stash_window_id" ]; then
    exit 0
fi

exec "$HOME/.config/niri/bin/summon-window.sh" --workspace "$focused_workspace_ref" --place-near-focused-window "$stash_window_id"

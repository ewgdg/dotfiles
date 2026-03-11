#!/bin/sh

set -eu

fallback_workspace="main"
niri_bin_dir="${HOME}/.config/niri/bin"

focused_window_json="$(
    niri msg -j focused-window 2>/dev/null || printf '{}'
)"
focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"

if [ -z "$focused_window_id" ]; then
    printf '%s: no focused window\n' "$0" >&2
    exit 1
fi

pinned_window_json="$(
    "$niri_bin_dir/pinned-window.sh" status-json 2>/dev/null \
        || printf '%s\n' '{"pinned":false,"id":""}'
)"
pinned_window_id="$(printf '%s' "$pinned_window_json" | jq -r 'if (.pinned // false) then (.id // "") else "" end')"
pinned_workspace_ref="$(
    printf '%s' "$pinned_window_json" \
        | jq -r '
            if (.pinned // false) | not then
                ""
            elif (.workspace_name // "") != "" then
                .workspace_name
            elif .workspace_id != null then
                (.workspace_id | tostring)
            else
                ""
            end
        '
)"
pinned_is_floating="$(printf '%s' "$pinned_window_json" | jq -r '.is_floating // false')"

move_focused_window_to_main_workspace() {
    exec niri msg action move-window-to-workspace "$fallback_workspace"
}

if [ -z "$pinned_window_id" ] || [ -z "$pinned_workspace_ref" ] || [ "$pinned_is_floating" = "true" ] || [ "$focused_window_id" = "$pinned_window_id" ]; then
    move_focused_window_to_main_workspace
fi

if ! niri msg action focus-window --id "$pinned_window_id" >/dev/null 2>&1; then
    move_focused_window_to_main_workspace
fi

exec "$niri_bin_dir/summon-window.sh" --workspace "$pinned_workspace_ref" --place-near-focused-window "$focused_window_id"

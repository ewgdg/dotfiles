#!/bin/sh

set -eu

focused_window_json="$(
    niri msg -j windows 2>/dev/null \
        | jq -c '
            map(select(.is_focused))
            | first // {}
        '
)"

window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"
is_floating="$(printf '%s' "$focused_window_json" | jq -r '.is_floating // false')"

if [ -z "$window_id" ]; then
    printf 'toggle-expand-focused-window: no focused window\n' >&2
    exit 1
fi

if [ "$is_floating" = "true" ]; then
    niri msg action toggle-window-floating >/dev/null 2>&1
fi

exec niri msg action maximize-column

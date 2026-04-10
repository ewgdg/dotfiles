#!/bin/sh

set -eu

if [ "$#" -ne 1 ]; then
    printf 'usage: %s <workspace-ref>\n' "$0" >&2
    exit 2
fi

target_workspace_ref="$1"

focused_window_json="$(
    niri msg -j focused-window 2>/dev/null || printf '{}'
)"
focused_window_id="$(printf '%s' "$focused_window_json" | jq -r '.id // empty')"

if [ -z "$focused_window_id" ]; then
    printf '%s: no focused window\n' "$0" >&2
    exit 1
fi

niri msg action focus-window-previous >/dev/null 2>&1 || true

exec niri msg action move-window-to-workspace --window-id "$focused_window_id" --focus false "$target_workspace_ref"

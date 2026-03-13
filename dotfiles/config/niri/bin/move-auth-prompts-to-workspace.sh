#!/bin/sh

set -eu

target_workspace="${1:-main}"
log_tag="move-auth-prompts"
runtime_dir="${XDG_RUNTIME_DIR:-}"
session_marker="${runtime_dir:+$runtime_dir/noctalia-first-unlock-auth-prompts.done}"

log() {
    message="$1"
    if command -v logger >/dev/null 2>&1; then
        logger -t "$log_tag" -- "$message"
    fi
    printf '%s: %s\n' "$log_tag" "$message"
}

if [ -z "$runtime_dir" ]; then
    log "XDG_RUNTIME_DIR is not set; skipping"
    exit 0
fi

if [ -e "$session_marker" ]; then
    log "session marker exists at $session_marker; skipping repeated unlock hook"
    exit 0
fi

touch "$session_marker"
log "created session marker at $session_marker"

prompt_window_ids="$(
    niri msg -j windows 2>/dev/null \
        | jq -r '
            map(select(
                (.app_id // "" | test("(?i)(org[.]kde[.]ksecretd|kwallet|1password(-quickaccess)?)"))
                or (.title // "" | test("(?i)(kwallet|wallet.*password|unlock.*wallet|1password|unlock)"))
            ))
            | .[].id
        '
)"

if [ -z "$prompt_window_ids" ]; then
    log "no matching auth prompts found for workspace=$target_workspace"
    exit 0
fi

for prompt_window_id in $prompt_window_ids; do
    log "moving prompt window id=$prompt_window_id to workspace=$target_workspace"
    "$HOME/.config/niri/bin/summon-window.sh" \
        --workspace "$target_workspace" \
        --float \
        --center \
        "$prompt_window_id"
done

exit 0

#!/bin/sh

set -eu

timeout_seconds="${1:-20}"
log_tag="move-unlock-prompts"

log() {
    message="$1"
    if command -v logger >/dev/null 2>&1; then
        logger -t "$log_tag" -- "$message"
    fi
    printf '%s: %s\n' "$log_tag" "$message"
}

focused_workspace_ref() {
    niri msg -j workspaces 2>/dev/null \
        | jq -r '
            map(select(.is_focused == true))
            | first
            | if . == null then empty else ((.name // "") as $name | if $name != "" then $name else (.idx | tostring) end) end
        '
}

unlock_prompt_window_ids() {
    niri msg -j windows 2>/dev/null \
        | jq -r '
            map(select(
                (.app_id // "" | test("(?i)(org[.]kde[.]ksecretd|kwallet|gcr-prompter|polkit|1password(-quickaccess)?|pinentry|ssh-askpass)"))
                or (.title // "" | test("(?i)(unlock|password|authentication required|authenticate|kwallet|wallet|1password|passphrase|pinentry)"))
            ))
            | .[].id
        '
}

target_workspace="$(focused_workspace_ref)"
if [ -z "$target_workspace" ]; then
    log "failed to detect focused workspace; skipping"
    exit 0
fi

log "watching unlock prompts for workspace=$target_workspace"

deadline=$(( $(date +%s) + timeout_seconds ))
while [ "$(date +%s)" -le "$deadline" ]; do
    prompt_window_ids="$(unlock_prompt_window_ids)"
    if [ -n "$prompt_window_ids" ]; then
        for prompt_window_id in $prompt_window_ids; do
            log "moving unlock prompt window id=$prompt_window_id to workspace=$target_workspace"
            "$HOME/.config/niri/bin/summon-window.sh" \
                --workspace "$target_workspace" \
                --float \
                --center \
                "$prompt_window_id"
        done
        exit 0
    fi
    sleep 1
done

log "no unlock prompt found within ${timeout_seconds}s"
exit 0

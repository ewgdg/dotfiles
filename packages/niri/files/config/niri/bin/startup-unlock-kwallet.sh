#!/bin/sh

set -eu

wallet_name="${1:-kdewallet}"
request_app_id="${2:-startup-unlocker}"
log_tag="startup-unlock-kwallet"

log() {
    message="$1"
    if command -v logger >/dev/null 2>&1; then
        logger -t "$log_tag" -- "$message"
    fi
    printf '%s: %s\n' "$log_tag" "$message"
}

# Match the common KWallet unlock dialog variants. Keep the title clause broad because
# the visible window can come from a helper rather than the main daemon.
prompt_window_id="$(
    niri msg -j windows 2>/dev/null \
        | jq -r '
            map(select(
                (.app_id // "" | test("(?i)(org[.]kde[.]ksecretd|kwallet|wallet)"))
                or (.title // "" | test("(?i)(kwallet|unlock.*wallet|wallet.*password)"))
            ))
            | sort_by(.focus_timestamp.secs // 0, .focus_timestamp.nanos // 0)
            | last
            | .id // empty
        '
)"

log "wallet_name=$wallet_name request_app_id=$request_app_id prompt_window_id=${prompt_window_id:-<none>}"

if [ -n "$prompt_window_id" ]; then
    log "existing kwallet prompt window id=$prompt_window_id found; skipping new unlock request"
    exit 0
fi

log "requesting wallet open over D-Bus"
exec qdbus6 org.kde.kwalletd6 /modules/kwalletd6 org.kde.KWallet.open "$wallet_name" 0 "$request_app_id" >/dev/null 2>&1

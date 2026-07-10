#!/bin/sh
set -eu

log_tag="restore-noctalia-lock-screen"

log() {
    printf '%s: %s\n' "$log_tag" "$*" >&2
}

is_locked() {
    [ -n "${XDG_SESSION_ID:-}" ] || return 1
    command -v loginctl >/dev/null 2>&1 || return 1
    [ "$(loginctl show-session "$XDG_SESSION_ID" -p LockedHint --value 2>/dev/null || true)" = "yes" ]
}

if ! is_locked; then
    log "not restoring lock screen: logind LockedHint is not yes"
    exit 0
fi

log "logind says session is locked; restoring Noctalia lock screen"

attempt=1
while [ "$attempt" -le 40 ]; do
    if noctalia msg session lock >/dev/null 2>&1; then
        log "Noctalia lock screen restored"
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 0.25
done

# Do not fail niri-shell.service; if compositor remains locked, another restart
# should retry once Noctalia IPC is ready.
log "failed to restore Noctalia lock screen after waiting for IPC"
exit 0

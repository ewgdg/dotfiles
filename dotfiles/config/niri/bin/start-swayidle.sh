#!/bin/sh

set -eu

if ! command -v swayidle >/dev/null 2>&1; then
    echo "swayidle not found in PATH; skipping idle setup" >&2
    exit 0
fi

# Override via environment variables if you want different timers.
lock_timeout_seconds="${NIRI_IDLE_LOCK_SECONDS:-300}"
monitor_off_timeout_seconds="${NIRI_IDLE_MONITOR_OFF_SECONDS:-330}"

lock_command='qs -c noctalia-shell ipc call lockScreen lock'
monitor_off_command='niri msg action power-off-monitors'

exec swayidle -w \
    timeout "$lock_timeout_seconds" "$lock_command" \
    timeout "$monitor_off_timeout_seconds" "$monitor_off_command" \
    before-sleep "$lock_command"

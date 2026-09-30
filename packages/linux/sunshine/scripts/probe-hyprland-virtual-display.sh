#!/usr/bin/env bash
# One-shot probe: can Sunshine stream a Hyprland headless (virtual) output?
# Run inside a real Hyprland session. Leaves no output or config behind.
#
# Checks, in order:
#   1. `hyprctl output create headless` yields a sized output
#      (if its GBM buffer allocation fails, it stays 0x0).
#   2. grim can grab it, so the output actually renders.
# Sunshine `capture = wlr` on a rendering headless output was tested separately
# on Hyprland 0.56.2 (a Moonlight stream connected and decoded frames). Sunshine's
# startup encoder check uses dummy frames, so it cannot stand in for a real stream.
set -euo pipefail

PROBE_OUTPUT="sunshine-probe"
PROBE_MODE="1920x1080@60"

[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || { echo "Run this inside a Hyprland session." >&2; exit 1; }
for cmd in hyprctl jq grim; do
    command -v "$cmd" >/dev/null || { echo "Missing command: $cmd" >&2; exit 1; }
done

work_dir="$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/hyprland-sunshine-probe.XXXXXX")"
remove_probe_output() { hyprctl output remove "$PROBE_OUTPUT" >/dev/null 2>&1 || true; }
trap remove_probe_output EXIT

probe_monitor() { hyprctl -j monitors all | jq -c --arg name "$PROBE_OUTPUT" '.[] | select(.name == $name) | {width, height, refreshRate, disabled}'; }
probe_width() { hyprctl -j monitors all | jq --arg name "$PROBE_OUTPUT" '[.[] | select(.name == $name) | .width][0] // 0'; }

echo "== Hyprland $(hyprctl -j version | jq -r .tag)"
hyprctl output create headless "$PROBE_OUTPUT"
hyprctl eval "hl.monitor({ output = \"$PROBE_OUTPUT\", disabled = false, mode = \"$PROBE_MODE\", position = \"auto\", scale = 1 })"

for _ in $(seq 1 30); do
    [[ "$(probe_width)" -gt 0 ]] && break
    sleep 0.1
done
echo "== 1. headless output: $(probe_monitor)"
if [[ "$(probe_width)" -eq 0 ]]; then
    echo "VERDICT: headless output never got a size -> use a dummy plug + capture = kms."
    exit 0
fi

if timeout 5 grim -o "$PROBE_OUTPUT" "$work_dir/grim.png" 2>"$work_dir/grim.err"; then
    echo "== 2. grim: ok ($(stat -c %s "$work_dir/grim.png") bytes)"
    echo "VERDICT: headless output renders -> capture = wlr, output_name = sunshine."
else
    echo "== 2. grim: FAILED: $(cat "$work_dir/grim.err")"
    echo "VERDICT: headless output is sized but does not render -> dummy plug + capture = kms."
fi
echo "Logs: $work_dir"

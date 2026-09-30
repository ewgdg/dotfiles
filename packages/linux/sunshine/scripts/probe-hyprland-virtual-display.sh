#!/usr/bin/env bash
# One-shot probe: can Sunshine stream a Hyprland headless (virtual) output?
# Run inside a real Hyprland session. Leaves no output or config behind.
#
# Checks, in order:
#   1. `hyprctl output create headless` yields a sized, rendering output
#      (on NVIDIA the GBM buffer allocation can fail and leave it 0x0).
#   2. grim can grab it (pixels exist; grim may use ext-image-copy-capture).
#   3. A throwaway Sunshine instance with `capture = wlr` on that output passes
#      its startup encoder probe, which captures real frames via zwlr_screencopy.
#      It uses its own ports/state, so the running Sunshine service is untouched.
set -euo pipefail

PROBE_OUTPUT="sunshine-probe"
PROBE_MODE="1920x1080@60"
# Offset from the default 47989 so the running service keeps its ports.
PROBE_SUNSHINE_PORT=48989
SUNSHINE_PROBE_SECONDS=25

[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || { echo "Run this inside a Hyprland session." >&2; exit 1; }
for cmd in hyprctl jq grim sunshine; do
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
else
    echo "== 2. grim: FAILED: $(cat "$work_dir/grim.err")"
fi

cat >"$work_dir/sunshine.conf" <<EOF
capture = wlr
output_name = $PROBE_OUTPUT
port = $PROBE_SUNSHINE_PORT
system_tray = disabled
log_path = $work_dir/sunshine.log
file_state = $work_dir/sunshine_state.json
credentials_file = $work_dir/credentials.json
file_apps = $work_dir/apps.json
EOF
echo '{"env":{},"apps":[]}' >"$work_dir/apps.json"

echo "== 3. Sunshine wlr probe (${SUNSHINE_PROBE_SECONDS}s)..."
timeout "$SUNSHINE_PROBE_SECONDS" sunshine "$work_dir/sunshine.conf" >/dev/null 2>&1 || true
# Strip timestamps and dedupe: the encoder probe repeats the monitor lines per codec.
grep -E 'wlgrab|Found monitor|Found (H.264|HEVC|AV1) encoder|Fatal|Unable to|Couldn.t' "$work_dir/sunshine.log" \
    | sed 's/^\[[^]]*\]: /   /' | awk '!seen[$0]++' || true

if grep -q "Selected monitor .*$PROBE_OUTPUT" "$work_dir/sunshine.log" && grep -qE 'Found (H.264|HEVC|AV1) encoder' "$work_dir/sunshine.log"; then
    echo "VERDICT: wlr capture works on the headless output -> capture = wlr, output_name = sunshine."
else
    echo "VERDICT: headless renders but Sunshine wlr capture failed -> portal capture with an auto-selecting xdph picker."
fi
echo "Logs: $work_dir"

#!/usr/bin/python3

"""
Prepare Hyprland outputs for Sunshine streaming, then restore them on cleanup.

This script is intended to be used via Sunshine's `global_prep_cmd`.

Usage:
  sunshine-prep-hyprland.py do --width WIDTH --height HEIGHT --fps FPS [--headless] [--solo] [--scale SCALE] [--inhibit]
  sunshine-prep-hyprland.py undo [--dormant-headless]

Modes:
- detected (default): Uses an existing monitor that supports the requested WxH@FPS.
- headless (`--headless`): Resizes the fixed `sunshine` headless output that the
  Hyprland config creates at startup (created here if missing) and focuses it.

Notes:
- Requires Hyprland (`hyprctl`) with a Lua config; monitor changes go through `hyprctl eval`.
- `undo` re-enables outputs disabled by `--solo`, then turns the `sunshine` output
  off unless `--dormant-headless` is passed, which parks it at 60 Hz instead.
- Pass `--inhibit` to prevent idle using systemd-inhibit while active.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional


HEADLESS_OUTPUT_NAME = "sunshine"
DORMANT_OUTPUT_FPS = 60
# Monitor rules apply on the next rendered frame, not synchronously with `hyprctl eval`.
MODE_APPLY_TIMEOUT_SECONDS = 2.0
INHIBIT_WHO = "sunshine"
INHIBIT_REASON = "sunshine-connection"
DEBUG_LOG = "/tmp/sunshine-prep-debug.log"

# Global flags to control debug logging
ENABLE_FILE_LOGGING = False
ENABLE_CONSOLE_LOGGING = True  # Default to True


def debug_write(message: str) -> None:
    """Write debug message to file and/or console if logging is enabled."""
    if ENABLE_FILE_LOGGING:
        try:
            with open(DEBUG_LOG, "a") as f:
                f.write(message)
        except Exception:
            pass  # Silently ignore logging errors

    if ENABLE_CONSOLE_LOGGING:
        print(message.rstrip())  # Remove trailing newlines for console


def ensure_hyprland_signature() -> bool:
    """Ensure HYPRLAND_INSTANCE_SIGNATURE is set by detecting it from socket directory."""

    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        debug_write(
            f"DEBUG: HYPRLAND_INSTANCE_SIGNATURE already set: {os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')}\n"
        )
        return True

    try:
        user_id = os.getuid()
        hypr_dir = f"/run/user/{user_id}/hypr"
        debug_write(f"DEBUG: Looking for signature in: {hypr_dir}\n")

        if not os.path.exists(hypr_dir):
            debug_write(f"DEBUG: Hypr directory does not exist: {hypr_dir}\n")
            return False

        # Get the signature directory (should be the only subdirectory)
        entries = os.listdir(hypr_dir)
        debug_write(f"DEBUG: Found entries in hypr dir: {entries}\n")
        for entry in entries:
            entry_path = os.path.join(hypr_dir, entry)
            if os.path.isdir(entry_path):
                os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = entry
                debug_write(f"DEBUG: Set HYPRLAND_INSTANCE_SIGNATURE to: {entry}\n")
                return True

        debug_write(f"DEBUG: No valid signature directory found\n")
        return False
    except (OSError, PermissionError) as e:
        debug_write(f"DEBUG: Exception in ensure_hyprland_signature: {e}\n")
        return False


def run_command(cmd: str, returncode_ok: bool = False) -> Optional[str]:
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            check=not returncode_ok,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        # If returncode_ok is True, we still want stdout regardless of rc
        return (res.stdout or "").strip()
    except subprocess.CalledProcessError as e:
        debug_write(f"ERROR: Command failed: {cmd}\n{e.stderr}\n")
        return None


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def lua_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    # JSON string escapes are valid Lua string escapes for these plain values.
    return json.dumps(str(value))


def set_monitor(
    name: str,
    mode: Optional[str] = None,
    scale: Optional[float] = None,
    disabled: bool = False,
) -> None:
    # Hyprland's Lua config rejects `hyprctl keyword`; runtime rules go through `eval`.
    # hl.monitor merges into an existing rule for the same output, so `disabled` is
    # always sent explicitly; otherwise an earlier disable would stick.
    fields: Dict[str, Any] = {"output": name, "disabled": disabled}
    if mode is not None:
        fields.update(mode=mode, position="auto")
    if scale is not None:
        fields["scale"] = scale
    body = ", ".join(f"{key} = {lua_literal(value)}" for key, value in fields.items())
    run_command(f"hyprctl eval {shlex.quote(f'hl.monitor({{ {body} }})')}", returncode_ok=True)


def hypr_json(subcmd: str) -> Optional[Any]:
    out = run_command(f"hyprctl -j {subcmd}")
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def get_monitors(include_disabled: bool = True) -> Optional[List[Dict[str, Any]]]:
    # Try broader query first if supported
    data = hypr_json("monitors all") if include_disabled else None
    if data is None:
        data = hypr_json("monitors")
    if isinstance(data, dict) and "monitors" in data:
        return data.get("monitors")  # some versions nest under a key
    if isinstance(data, list):
        return data
    return None


def round_hz(val: Any) -> Optional[int]:
    try:
        return int(round(float(val)))
    except Exception:
        return None




def monitor_matches_current(name: str, width: int, height: int, fps: int) -> bool:
    mons = get_monitors(include_disabled=False) or []
    for m in mons:
        if m.get("name") != name:
            continue
        mw = int(m.get("width", 0))
        mh = int(m.get("height", 0))
        mhz = round_hz(m.get("refreshRate"))
        return (
            mw == width
            and mh == height
            and (mhz == int(fps) if mhz is not None else True)
        )
    return False


def try_set_monitor_mode(name: str, width: int, height: int, fps: int) -> bool:
    # hyprctl returns 0 even on some errors; verify by re-reading state
    set_monitor(name, mode=f"{width}x{height}@{fps}", scale=1)
    return monitor_matches_current(name, width, height, fps)


def compute_scale(scale_arg: Optional[str], width: int, height: int) -> float:
    """Compute scale based solely on client height.

    Rules:
    - Numeric scale_arg -> clamp to [1.0, 3.0].
    - 'auto' / 'heuristic' / 'client-auto' / 'dpi-auto' -> linear: scale = height / 1080.0, clamped to [1.0, 3.0], rounded to 2 decimals.
      Examples: 1080->1.0, 1440->1.33, 2160->2.0.
    - None -> 1.0.
    """
    if not scale_arg:
        return 1.0

    scale_mode = scale_arg.lower()
    if scale_mode not in {"auto", "heuristic", "client-auto", "dpi-auto"}:
        try:
            v = float(scale_arg)
            return max(1.0, min(v, 3.0))
        except Exception:
            return 1.0

    if scale_mode in {"auto", "heuristic", "client-auto", "dpi-auto"}:
        s = height / 1080.0 if height else 1.0
        s = max(1.0, min(s, 3.0))
        return round(s, 2)

    return 1.0


def disable_other_monitors(selected: str) -> None:
    mons = get_monitors(include_disabled=True) or []
    for m in mons:
        name = m.get("name")
        if not name or name == selected:
            continue
        set_monitor(name, disabled=True)


def enable_runtime_inhibit() -> Optional[int]:
    try:
        p = subprocess.Popen(
            [
                "systemd-inhibit",
                f"--who={INHIBIT_WHO}",
                "--what=idle",
                f"--why={INHIBIT_REASON}",
                "--",
                "sleep",
                "infinity",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        debug_write(f"DEBUG: systemd-inhibit PID: {p.pid}\n")
        return p.pid
    except Exception as e:
        debug_write(f"ERROR: Failed to start systemd-inhibit: {e}\n")
        return None


def kill_runtime_inhibit() -> None:
    # We don't track the PID anymore; kill by pattern
    run_command(f"pkill -f {INHIBIT_REASON}", returncode_ok=True)


def find_monitor(name: str) -> Optional[Dict[str, Any]]:
    for monitor in get_monitors(include_disabled=True) or []:
        if monitor.get("name") == name:
            return monitor
    return None


def wait_for_mode(name: str, width: int, height: int, fps: int) -> bool:
    deadline = time.monotonic() + MODE_APPLY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if monitor_matches_current(name, width, height, fps):
            return True
        time.sleep(0.1)
    return monitor_matches_current(name, width, height, fps)


def ensure_headless_output() -> None:
    if find_monitor(HEADLESS_OUTPUT_NAME) is None:
        run_command(f"hyprctl output create headless {HEADLESS_OUTPUT_NAME}", returncode_ok=True)
    if find_monitor(HEADLESS_OUTPUT_NAME) is None:
        raise RuntimeError(f"Failed to create Hyprland headless output '{HEADLESS_OUTPUT_NAME}'.")


def focus_monitor(name: str) -> None:
    # Remote input must land on the captured output even when other outputs stay enabled.
    run_command(f"hyprctl dispatch {shlex.quote(f'hl.dsp.focus({{ monitor = {lua_literal(name)} }})')}", returncode_ok=True)


def select_detected_monitor(width: int, height: int, fps: int) -> str:
    monitors = [
        m
        for m in (get_monitors(include_disabled=True) or [])
        if m.get("name") and m.get("name") != HEADLESS_OUTPUT_NAME
    ]
    # Prioritize DP monitors
    monitors.sort(key=lambda m: 0 if str(m.get("name", "")).startswith(("DP-", "eDP-", "DP")) else 1)
    for monitor in monitors:
        name = monitor["name"]
        debug_write(f"DEBUG: Trying monitor {name}\n")
        if try_set_monitor_mode(name, width, height, fps):
            return name
    raise RuntimeError(f"No monitor supports {width}x{height}@{fps}.")


def do_action(
    width: int,
    height: int,
    fps: int,
    *,
    headless: bool,
    solo: bool,
    inhibit: bool,
    scale_arg: Optional[str],
) -> None:
    # tiny wake so remote cursor shows up quickly (optional)
    if which("ydotool"):
        run_command("ydotool mousemove -x 1 -y 1", returncode_ok=True)

    if headless:
        ensure_headless_output()
        selected = HEADLESS_OUTPUT_NAME
    else:
        selected = select_detected_monitor(width, height, fps)

    scale = compute_scale(scale_arg, width, height)
    set_monitor(selected, mode=f"{width}x{height}@{fps}", scale=scale)
    if not wait_for_mode(selected, width, height, fps):
        raise RuntimeError(f"Monitor {selected} did not switch to {width}x{height}@{fps}.")
    debug_write(f"INFO: Using monitor: {selected} at {width}x{height}@{fps}, scale {scale}\n")

    focus_monitor(selected)
    if solo:
        disable_other_monitors(selected)
    if inhibit:
        enable_runtime_inhibit()


def reenable_disabled_monitors() -> None:
    for monitor in get_monitors(include_disabled=True) or []:
        name = monitor.get("name")
        if name and name != HEADLESS_OUTPUT_NAME and monitor.get("disabled"):
            set_monitor(name, disabled=False)


def park_headless_output_dormant() -> None:
    # Keep wl_output present: disabling the output hot-removes it, which Wine/XWayland
    # clients see as a monitor unplug on every stream transition. Keep the stream
    # resolution and scale too; only drop the refresh rate.
    monitor = find_monitor(HEADLESS_OUTPUT_NAME)
    if monitor is None:
        debug_write(f"WARNING: {HEADLESS_OUTPUT_NAME} output missing; nothing to park.\n")
        return
    set_monitor(
        HEADLESS_OUTPUT_NAME,
        mode=f"{monitor['width']}x{monitor['height']}@{DORMANT_OUTPUT_FPS}",
        scale=float(monitor["scale"]),
    )


def restore_action(*, dormant_headless: bool) -> None:
    kill_runtime_inhibit()
    if not ensure_hyprland_signature():
        debug_write("WARNING: Hyprland not running or signature not found. Skipping monitor restore.\n")
        return

    reenable_disabled_monitors()
    if dormant_headless:
        park_headless_output_dormant()
    else:
        set_monitor(HEADLESS_OUTPUT_NAME, disabled=True)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hyprland monitor prep for Sunshine")
    sub = parser.add_subparsers(dest="action", help="Action to perform")

    p_do = sub.add_parser("do", help="Select and configure an output for streaming")
    p_do.add_argument("--width", type=int, help="Screen width in pixels")
    p_do.add_argument("--height", type=int, help="Screen height in pixels")
    p_do.add_argument("--fps", type=int, help="Refresh rate in Hz")
    p_do.add_argument(
        "--headless",
        action="store_true",
        help=f"Stream the fixed '{HEADLESS_OUTPUT_NAME}' headless output",
    )
    p_do.add_argument(
        "--scale",
        type=str,
        help="Hypr scale (e.g. 1, 1.25, 1.5) or 'auto'/'heuristic'/'client-auto'/'dpi-auto' for heuristic",
    )
    p_do.add_argument("--solo", action="store_true", help="Disable all other outputs during session")
    p_do.add_argument("--inhibit", action="store_true", help="Inhibit idle with systemd-inhibit while streaming.")
    p_do.add_argument("--log-file", action="store_true", help="Enable debug logging to file")
    p_do.add_argument("--no-log-console", action="store_true", help="Disable debug logging to console")

    p_undo = sub.add_parser("undo", help="Restore outputs after streaming")
    p_undo.add_argument(
        "--dormant-headless",
        action="store_true",
        help=f"Park the '{HEADLESS_OUTPUT_NAME}' output at {DORMANT_OUTPUT_FPS} Hz instead of turning it off",
    )
    p_undo.add_argument("--log-file", action="store_true", help="Enable debug logging to file")
    p_undo.add_argument("--no-log-console", action="store_true", help="Disable debug logging to console")
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    args = parse_args(argv)
    if not args.action:
        debug_write(__doc__ + "\n")
        sys.exit(1)

    if args.action == "do":
        width = args.width or int(os.environ.get("SUNSHINE_CLIENT_WIDTH", "0") or 0)
        height = args.height or int(os.environ.get("SUNSHINE_CLIENT_HEIGHT", "0") or 0)
        fps = args.fps or int(os.environ.get("SUNSHINE_CLIENT_FPS", "0") or 0)
        if not (width and height and fps):
            debug_write("ERROR: Missing required --width/--height/--fps (or SUNSHINE_CLIENT_* envs).\n")
            sys.exit(1)
        if not which("hyprctl"):
            debug_write("ERROR: hyprctl not found. Are you running Hyprland?\n")
            sys.exit(1)
        if not ensure_hyprland_signature():
            debug_write("ERROR: HYPRLAND_INSTANCE_SIGNATURE not set! (is hyprland running?)\n")
            sys.exit(1)
        do_action(
            width,
            height,
            fps,
            headless=args.headless,
            solo=args.solo,
            inhibit=args.inhibit,
            scale_arg=args.scale,
        )
    elif args.action == "undo":
        restore_action(dormant_headless=args.dormant_headless)


if __name__ == "__main__":
    # Check for logging flags early
    if "--log-file" in sys.argv:
        ENABLE_FILE_LOGGING = True
    if "--no-log-console" in sys.argv:
        ENABLE_CONSOLE_LOGGING = False

    main(sys.argv[1:])

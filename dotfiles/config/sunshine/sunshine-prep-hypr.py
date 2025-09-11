#!/usr/bin/python3

"""
Prepare Hyprland outputs for Sunshine streaming using a headless (virtual) output
when possible, then restore/cleanup.

Usage:
  sunshine-prep-hypr.py do --width WIDTH --height HEIGHT --fps FPS [--name NAME] [--solo] [--mode MODE]
  sunshine-prep-hypr.py undo

Modes:
- detected (default): Uses existing monitor that supports the requested resolution/fps
- headless: Creates a virtual headless output named 'HEADLESS-sunshine'

Defaults:
- Uses detected mode to find a suitable existing monitor
- Does NOT disable physical monitors unless `--solo` is passed.

Notes:
- Requires Hyprland (`hyprctl`). Headless outputs need Hyprland with `output create headless` support.
- If headless creation fails, falls back to selecting an existing monitor that matches WxH@FPS.
- Prevents idle using systemd-inhibit while active.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
import time


DEFAULT_HEADLESS_NAME = os.environ.get("SUNSHINE_HEADLESS_NAME", "HEADLESS-sunshine")
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
        debug_write(f"DEBUG: HYPRLAND_INSTANCE_SIGNATURE already set: {os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')}\n")
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


def set_monitor_keyword(spec: str) -> None:
    run_command(f"hyprctl keyword monitor '{spec}'", returncode_ok=True)


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


def create_headless_output(name: str) -> Optional[str]:
    """Create a headless output with a given name; returns the resolved name."""
    # If it already exists, just return it
    mons = get_monitors(include_disabled=True) or []
    for m in mons:
        if m.get("name") == name:
            return name

    out = run_command(f"hyprctl output create headless {name}", returncode_ok=True)
    # Validate creation by listing monitors again
    mons2 = get_monitors(include_disabled=True) or []
    for m in mons2:
        if m.get("name") == name:
            return name
    return None


def output_exists(name: str) -> bool:
    mons = get_monitors(include_disabled=True) or []
    return any(m.get("name") == name for m in mons)


def get_monitor_id(name: str) -> Optional[int]:
    """Get monitor ID by name."""
    mons = get_monitors(include_disabled=True) or []
    for m in mons:
        if m.get("name") == name:
            return m.get("id")
    return None


def is_headless_name(name: Optional[str], preferred: Optional[str]) -> bool:
    if not name:
        return False
    if preferred and name == preferred:
        return True
    # Default and common Hypr headless naming
    if name == DEFAULT_HEADLESS_NAME:
        return True
    if str(name).upper().startswith("HEADLESS"):
        return True
    return False


def clients_on_monitor_id(monitor_id: int) -> int:
    """Return count of mapped clients on a given monitor ID."""
    data = hypr_json("clients")
    if not isinstance(data, list):
        return 0
    cnt = 0
    for c in data:
        try:
            # Check if client is mapped and on the correct monitor
            # Note: c.get("monitor") might return name or ID depending on Hyprland version
            client_monitor = c.get("monitor")
            mapped = c.get("mapped", False)
            if mapped and (client_monitor == monitor_id or client_monitor == str(monitor_id)):
                cnt += 1
        except Exception:
            continue
    return cnt


def clients_on_monitor(name: str) -> int:
    """Return count of mapped clients on a given monitor name."""
    monitor_id = get_monitor_id(name)
    if monitor_id is None:
        return 0
    return clients_on_monitor_id(monitor_id)


def install_guard_signal_traps() -> None:
    def _handler(signum, frame):
        try:
            restore_action()
        finally:
            os._exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


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
    spec = f"{name},{width}x{height}@{fps},auto,1"
    # hyprctl returns 0 even on some errors; verify by re-reading state
    set_monitor_keyword(spec)
    return monitor_matches_current(name, width, height, fps)


def compute_scale(scale_arg: Optional[str], width: int, height: int) -> float:
    """Compute scale based solely on client height.

    Rules:
    - Numeric scale_arg -> clamp to [1.0, 3.0].
    - 'auto' -> linear: scale = height / 1080.0, clamped to [1.0, 3.0], rounded to 2 decimals.
      Examples: 1080->1.0, 1440->1.33, 2160->2.0.
    - None -> 1.0.
    """
    if scale_arg and scale_arg.lower() != "auto":
        try:
            v = float(scale_arg)
            return max(1.0, min(v, 3.0))
        except Exception:
            return 1.0

    if scale_arg and scale_arg.lower() == "auto":
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
        set_monitor_keyword(f"{name},disable")


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


def do_action(
    width: int,
    height: int,
    fps: int,
    name: str,
    solo: bool,
    scale_arg: Optional[str] = None,
    mode: str = "detected",
) -> Optional[int]:
    if not which("hyprctl"):
        debug_write("ERROR: hyprctl not found. Are you running Hyprland?\n")
        sys.exit(1)
    
    if not ensure_hyprland_signature():
        debug_write("ERROR: HYPRLAND_INSTANCE_SIGNATURE not set! (is hyprland running?)\n")
        sys.exit(1)

    # tiny wake so remote cursor shows up quickly (optional)
    if which("ydotool"):
        run_command("ydotool mousemove -x 1 -y 1", returncode_ok=True)

    if mode == "headless":
        # Use headless virtual output
        created_name = create_headless_output(name)
        if created_name:
            # Nothing to persist; we operate statelessly now
            # Compute scale (supports --scale auto heuristic)
            scale = compute_scale(scale_arg, width, height)
            # Set requested mode on the headless output
            spec = f"{created_name},{width}x{height}@{fps},auto,{scale}"
            set_monitor_keyword(spec)
            if solo:
                disable_other_monitors(created_name)
            debug_write(f"INFO: Using headless output: {created_name} at {width}x{height}@{fps}\n")
            enable_runtime_inhibit()
            return get_monitor_id(created_name)
        else:
            # Fallback to detected mode if headless creation fails
            debug_write("DEBUG: Headless output creation failed; falling back to detected mode.\n")
            mode = "detected"

    if mode == "detected":
        # Default mode: detected - find existing monitor that supports requested mode
        debug_write(f"DEBUG: Looking for monitor supporting {width}x{height}@{fps}...\n")
        mons = [
            m
            for m in (get_monitors(include_disabled=True) or [])
            if m.get("name") and not is_headless_name(m.get("name"), None)
        ]
        # Prioritize DP monitors
        mons.sort(
            key=lambda m: 0
            if str(m.get("name", "")).startswith(("DP-", "eDP-", "DP"))
            else 1
        )
        
        selected: Optional[str] = None
        for m in mons:
            mname = m.get("name")
            if not mname:
                continue
            debug_write(f"DEBUG: Trying monitor {mname}\n")
            if try_set_monitor_mode(mname, width, height, fps):
                selected = mname
                break
        
        if not selected:
            debug_write(f"ERROR: No monitor supports {width}x{height}@{fps}.\n")
            sys.exit(1)
        
        # Apply scale to selected monitor
        scale = compute_scale(scale_arg, width, height)
        set_monitor_keyword(f"{selected},{width}x{height}@{fps},auto,{scale}")
        debug_write(f"INFO: Using monitor: {selected} at {width}x{height}@{fps}\n")
        
        if solo:
            disable_other_monitors(selected)
        
        enable_runtime_inhibit()
        return get_monitor_id(selected)


def _kill_guard_processes() -> None:
    """Terminate any background guard processes started by this script.

    Uses a precise pattern that matches this script's name followed by
    the 'guard' subcommand to avoid unrelated processes.
    """
    try:
        script_name = os.path.basename(sys.argv[0]) or "sunshine-prep-hypr.py"
        # Best-effort; ignore errors if none are running
        run_command(f"pkill -f \"{script_name} guard\"", returncode_ok=True)
    except Exception:
        pass


def restore_action(
    monitor_to_disable: Optional[str] = None, *, from_guard: bool = False
) -> None:
    debug_write("DEBUG: Starting restore action\n")
    
    # Check if Hyprland is running
    if not ensure_hyprland_signature():
        debug_write("DEBUG: HYPRLAND_INSTANCE_SIGNATURE not set, skipping monitor restore\n")
        debug_write("WARNING: Hyprland not running or signature not found. Skipping monitor restore.\n")
        # Still try to kill processes
        if not from_guard:
            _kill_guard_processes()
        kill_runtime_inhibit()
        return
    
    # If undo() is called manually, proactively stop any background guards
    if not from_guard:
        debug_write("DEBUG: Killing background guard processes\n")
        _kill_guard_processes()

    debug_write("DEBUG: Killing runtime inhibit processes\n")
    kill_runtime_inhibit()

    # Single pass: disable headless, (re)enable physicals at preferred
    debug_write("DEBUG: Getting monitor list for restore\n")
    mons = get_monitors(include_disabled=True) or []
    debug_write(f"DEBUG: Found {len(mons)} monitors\n")
    
    for m in mons:
        name = m.get("name")
        if not name:
            continue
        debug_write(f"DEBUG: Processing monitor: {name}\n")
        if is_headless_name(name, monitor_to_disable):
            debug_write(f"DEBUG: Disabling headless monitor: {name}\n")
            set_monitor_keyword(f"{name},disable")
            continue
        active = bool(m.get("active", False)) and int(m.get("width", 0)) > 0
        if not active:
            debug_write(f"DEBUG: Re-enabling physical monitor: {name}\n")
            set_monitor_keyword(f"{name},preferred,auto,1")
    
    debug_write("DEBUG: Restore action completed\n")


def guard_action(
    proc: Optional[str],
    pid: Optional[int],
    interval: int,
    grace: int,
    timeout: Optional[int],
    mode: str,
    monitor: Optional[str],
    initial_delay: int = 0,
    monitor_id: Optional[int] = None,
) -> None:
    """Background guard: watches either a process or headless activity and restores when done."""
    # Initial delay to allow monitor connection to stabilize
    if initial_delay > 0:
        debug_write(f"DEBUG: Guard waiting {initial_delay}s for monitor stabilization...\n")
        time.sleep(initial_delay)
    
    start = time.time()
    misses = 0

    # Resolve monitor: prefer ID, fall back to name, then default
    mon_id = monitor_id
    mon_name = monitor or DEFAULT_HEADLESS_NAME

    def _alive_proc() -> bool:
        if pid:
            out = run_command(f"ps -p {pid} -o pid=", returncode_ok=True)
            return bool(out)
        if proc:
            out = run_command(f"pgrep -x {proc}", returncode_ok=True)
            return bool(out)
        return True

    def _alive_activity() -> bool:
        # Prefer monitor ID for robustness
        if mon_id is not None:
            return clients_on_monitor_id(mon_id) > 0
        # Fallback to monitor name
        if not mon_name or not output_exists(mon_name):
            # If the output was already removed, we can consider not alive
            return False
        return clients_on_monitor(mon_name) > 0

    def _alive() -> bool:
        if mode == "proc":
            return _alive_proc()
        if mode == "pid":
            return _alive_proc()
        if mode == "activity":
            return _alive_activity()
        # default: activity
        return _alive_activity()

    while True:
        if timeout and time.time() - start > timeout:
            debug_write("DEBUG: guard: timeout reached; performing restore.\n")
            break
        if not _alive():
            misses += 1
            if misses >= max(grace, 1):
                debug_write("DEBUG: guard: condition met; performing restore.\n")
                break
        else:
            misses = 0
        time.sleep(max(1, interval))

    try:
        restore_action(mon_name if mode == "activity" else None, from_guard=True)
    except Exception as e:
        debug_write(f"ERROR: guard: restore failed: {e}\n")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hyprland monitor prep for Sunshine")
    sub = parser.add_subparsers(dest="action", help="Action to perform")

    p_do = sub.add_parser(
        "do", help="Create a headless monitor at a requested mode (or fallback)"
    )
    p_do.add_argument("--width", type=int, help="Screen width in pixels")
    p_do.add_argument("--height", type=int, help="Screen height in pixels")
    p_do.add_argument("--fps", type=int, help="Refresh rate in Hz")
    p_do.add_argument(
        "--name",
        type=str,
        default=os.environ.get("SUNSHINE_HEADLESS_NAME", "HEADLESS-sunshine"),
        help="Headless output name",
    )
    p_do.add_argument(
        "--scale",
        type=str,
        help="Hypr scale (e.g. 1, 1.25, 1.5) or 'auto' for heuristic",
    )
    p_do.add_argument(
        "--solo",
        action="store_true",
        help="Disable all non-headless outputs during session",
    )
    p_do.add_argument(
        "--guard",
        action="store_true", 
        help="Enable background guard for auto-cleanup (disabled by default)",
    )
    p_do.add_argument(
        "--guard-proc",
        type=str,
        default=os.environ.get("SUNSHINE_GUARD_PROCESS", "sunshine"),
        help="Process name to watch for auto-cleanup (proc mode)",
    )
    p_do.add_argument(
        "--guard-interval", type=int, default=5, help="Guard polling interval (seconds)"
    )
    p_do.add_argument(
        "--guard-grace", type=int, default=2, help="Consecutive misses before restore"
    )
    p_do.add_argument(
        "--guard-timeout",
        type=int,
        default=0,
        help="Optional timeout to force restore (seconds)",
    )
    p_do.add_argument(
        "--guard-mode",
        type=str,
        choices=["activity", "proc", "pid"],
        default=os.environ.get("SUNSHINE_GUARD_MODE", "activity"),
        help="Guard strategy: activity (default), proc, or pid",
    )
    p_do.add_argument(
        "--guard-monitor",
        type=str,
        help="Monitor name to watch in activity mode (defaults to created headless)",
    )
    p_do.add_argument(
        "--log-file",
        action="store_true",
        help="Enable debug logging to file",
    )
    p_do.add_argument(
        "--no-log-console",
        action="store_true",
        help="Disable debug logging to console",
    )
    p_do.add_argument(
        "--guard-delay",
        type=int,
        default=3,
        help="Delay in seconds before starting guard process (default: 3)",
    )
    p_do.add_argument(
        "--mode",
        type=str,
        choices=["detected", "headless"],
        default="detected",
        help="Output mode: detected (use existing monitor, default) or headless (create virtual output)",
    )

    p_undo = sub.add_parser(
        "undo", help="Restore monitors and remove headless output(s)"
    )
    p_undo.add_argument(
        "--name",
        type=str,
        default=DEFAULT_HEADLESS_NAME,
        help="Headless output name to remove (if present)",
    )
    p_guard = sub.add_parser(
        "guard", help="Run background guard and auto-restore on exit"
    )
    p_guard.add_argument(
        "--proc", type=str, default=os.environ.get("SUNSHINE_GUARD_PROCESS", "sunshine")
    )
    p_guard.add_argument("--pid", type=int)
    p_guard.add_argument("--interval", type=int, default=5)
    p_guard.add_argument("--grace", type=int, default=2)
    p_guard.add_argument("--timeout", type=int, default=0)
    p_guard.add_argument(
        "--mode",
        type=str,
        choices=["activity", "proc", "pid"],
        default=os.environ.get("SUNSHINE_GUARD_MODE", "activity"),
    )
    p_guard.add_argument(
        "--monitor", type=str, help="Monitor name to watch in activity mode"
    )
    p_guard.add_argument(
        "--monitor-id", type=int, help="Monitor ID to watch in activity mode (preferred over --monitor)"
    )
    p_guard.add_argument(
        "--initial-delay", type=int, default=0, help="Initial delay before starting guard"
    )
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
        debug_write(f"DEBUG: Resolved values - width: {width}, height: {height}, fps: {fps}\n")
        if not (width and height and fps):
            debug_write("DEBUG: Missing width/height/fps - exiting with code 1\n")
            debug_write(
                "ERROR: Missing required --width/--height/--fps (or SUNSHINE_CLIENT_* envs).\n"
            )
            sys.exit(1)
        selected_monitor_id = None
        # Try to create headless and configure
        try:
            selected_monitor_id = do_action(width, height, fps, args.name, args.solo, args.scale, args.mode)
        except SystemExit:
            raise
        except Exception as e:
            debug_write(f"ERROR: Error during do_action: {e}\n")
        # Spawn a background guard if enabled
        if args.guard:
            # Pass delay to guard process instead of blocking main process
            guard_delay = max(0, args.guard_delay)
            
            # Use the requested guard mode - activity mode works for both headless and physical monitors
            guard_mode = args.guard_mode
            cmd = [
                sys.executable or "python3",
                sys.argv[0],
                "guard",
                "--proc",
                args.guard_proc,
                "--interval",
                str(args.guard_interval),
                "--grace",
                str(args.guard_grace),
                "--mode",
                guard_mode,
                "--initial-delay",
                str(guard_delay),
            ]
            if args.guard_mode == "pid" and os.getppid() > 1:
                cmd += ["--pid", str(os.getppid())]
            # Always pass the monitor ID for activity guard
            if selected_monitor_id is not None:
                cmd += ["--monitor-id", str(selected_monitor_id)]
            elif args.guard_monitor:
                # Fallback to monitor name if ID not available
                cmd += ["--monitor", args.guard_monitor]
            if args.guard_timeout:
                cmd += ["--timeout", str(args.guard_timeout)]
            
            try:
                subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                debug_write("INFO: Started background guard for auto-restore.\n")
            except Exception as e:
                debug_write(f"DEBUG: Failed to start guard: {e}\n")
                debug_write(f"ERROR: Failed to start guard: {e}\n")
    elif args.action == "undo":
        try:
            restore_action(args.name)
        except Exception as e:
            debug_write(f"DEBUG: Error during undo: {e}\n")
            debug_write(f"ERROR: Error during undo: {e}\n")
            sys.exit(1)
    elif args.action == "guard":
        install_guard_signal_traps()
        timeout = args.timeout if args.timeout and args.timeout > 0 else None
        guard_action(
            args.proc,
            args.pid,
            args.interval,
            args.grace,
            timeout,
            args.mode,
            args.monitor,
            args.initial_delay,
            args.monitor_id,
        )


if __name__ == "__main__":
    # Check for logging flags early
    if "--log-file" in sys.argv:
        ENABLE_FILE_LOGGING = True
    if "--no-log-console" in sys.argv:
        ENABLE_CONSOLE_LOGGING = False
    
    # Initial debug logging only if enabled
    if ENABLE_FILE_LOGGING:
        import datetime
        is_main_do_command = len(sys.argv) > 1 and sys.argv[1] == "do"
        mode = "w" if is_main_do_command else "a"
        
        try:
            with open(DEBUG_LOG, mode) as f:
                f.write(f"\n=== {datetime.datetime.now()} - ENTRY POINT ===\n")
                f.write(f"DEBUG: Full sys.argv: {sys.argv}\n")
                f.write(f"DEBUG: CWD: {os.getcwd()}\n")
                f.write(f"DEBUG: Script path: {sys.argv[0]}\n")
                f.flush()
        except Exception:
            pass  # Silently ignore logging errors
    
    main(sys.argv[1:])

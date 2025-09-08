#!/usr/bin/env python3

"""
Prepare Hyprland outputs for Sunshine streaming using a headless (virtual) output
when possible, then restore/cleanup.

Usage:
  sunshine-prep-hypr.py do --width WIDTH --height HEIGHT --fps FPS [--name NAME] [--solo]
  sunshine-prep-hypr.py undo

Defaults:
- Creates a headless output named 'Sunshine-HEADLESS' and sets it to WxH@FPS.
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


DEFAULT_HEADLESS_NAME = os.environ.get("SUNSHINE_HEADLESS_NAME", "Sunshine-HEADLESS")
INHIBIT_WHO = "sunshine"
INHIBIT_REASON = "sunshine-connection"


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
        sys.stderr.write(f"Command failed: {cmd}\n{e.stderr}\n")
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


def clients_on_monitor(name: str) -> int:
    """Return count of mapped clients on a given monitor."""
    data = hypr_json("clients")
    if not isinstance(data, list):
        return 0
    cnt = 0
    for c in data:
        try:
            if c.get("mapped") and c.get("monitor") == name:
                cnt += 1
        except Exception:
            continue
    return cnt


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
        print(f"systemd-inhibit PID: {p.pid}")
        return p.pid
    except Exception as e:
        sys.stderr.write(f"Failed to start systemd-inhibit: {e}\n")
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
) -> None:
    if not which("hyprctl"):
        print("hyprctl not found. Are you running Hyprland?")
        sys.exit(1)

    # tiny wake so remote cursor shows up quickly (optional)
    if which("ydotool"):
        run_command("ydotool mousemove -x 1 -y 1", returncode_ok=True)

    # Prefer headless virtual output for simplicity
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
        print(f"Using headless output: {created_name} at {width}x{height}@{fps}")
        enable_runtime_inhibit()
        return

    # Fallback path: no headless backend available, try existing monitors
    print("Headless output creation failed; falling back to existing monitors.")
    mons = [
        m
        for m in (get_monitors(include_disabled=False) or [])
        if int(m.get("width", 0)) > 0
    ]
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
        if try_set_monitor_mode(mname, width, height, fps):
            selected = mname
            break
    if not selected:
        print(f"No monitor accepted {width}x{height}@{fps}.")
        sys.exit(1)
    # Apply scale to selected monitor as well
    scale = compute_scale(scale_arg, width, height)
    set_monitor_keyword(f"{selected},{width}x{height}@{fps},auto,{scale}")
    print(f"Selected monitor: {selected}")
    disable_other_monitors(selected)
    enable_runtime_inhibit()


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
    # If undo() is called manually, proactively stop any background guards
    if not from_guard:
        _kill_guard_processes()

    kill_runtime_inhibit()

    # Single pass: disable headless, (re)enable physicals at preferred
    mons = get_monitors(include_disabled=True) or []
    for m in mons:
        name = m.get("name")
        if not name:
            continue
        if is_headless_name(name, monitor_to_disable):
            set_monitor_keyword(f"{name},disable")
            continue
        active = bool(m.get("active", False)) and int(m.get("width", 0)) > 0
        if not active:
            set_monitor_keyword(f"{name},preferred,auto,1")


def guard_action(
    proc: Optional[str],
    pid: Optional[int],
    interval: int,
    grace: int,
    timeout: Optional[int],
    mode: str,
    monitor: Optional[str],
) -> None:
    """Background guard: watches either a process or headless activity and restores when done."""
    start = time.time()
    misses = 0

    # Resolve monitor name: prefer explicit; fall back to conventional default
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
            print("guard: timeout reached; performing restore.")
            break
        if not _alive():
            misses += 1
            if misses >= max(grace, 1):
                print("guard: condition met; performing restore.")
                break
        else:
            misses = 0
        time.sleep(max(1, interval))

    try:
        restore_action(mon_name if mode == "activity" else None, from_guard=True)
    except Exception as e:
        sys.stderr.write(f"guard: restore failed: {e}\n")


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
        default=os.environ.get("SUNSHINE_HEADLESS_NAME", "Sunshine-HEADLESS"),
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
        "--no-guard",
        action="store_true",
        help="Do not start a background guard for cleanup",
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
        "--monitor", type=str, help="Monitor to watch in activity mode"
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    args = parse_args(argv)
    if not args.action:
        print(__doc__)
        sys.exit(1)

    if args.action == "do":
        width = args.width or int(os.environ.get("SUNSHINE_CLIENT_WIDTH", "0") or 0)
        height = args.height or int(os.environ.get("SUNSHINE_CLIENT_HEIGHT", "0") or 0)
        fps = args.fps or int(os.environ.get("SUNSHINE_CLIENT_FPS", "0") or 0)
        if not (width and height and fps):
            print(
                "Missing required --width/--height/--fps (or SUNSHINE_CLIENT_* envs)."
            )
            sys.exit(1)
        headless_created = False
        # Try to create headless and configure
        try:
            do_action(width, height, fps, args.name, args.solo, args.scale)
            headless_created = output_exists(args.name)
        except SystemExit:
            raise
        except Exception as e:
            sys.stderr.write(f"Error during do_action: {e}\n")
        # Spawn a background guard unless disabled
        if not args.no_guard:
            # Auto-switch guard mode to proc if headless was not created
            guard_mode = args.guard_mode
            if guard_mode == "activity" and not headless_created:
                guard_mode = "proc"
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
            ]
            if args.guard_mode == "pid" and os.getppid() > 1:
                cmd += ["--pid", str(os.getppid())]
            # Always pass the monitor name for activity guard
            cmd += ["--monitor", args.guard_monitor or args.name]
            if args.guard_timeout:
                cmd += ["--timeout", str(args.guard_timeout)]
            try:
                subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                print("Started background guard for auto-restore.")
            except Exception as e:
                sys.stderr.write(f"Failed to start guard: {e}\n")
    elif args.action == "undo":
        restore_action(args.name)
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
        )


if __name__ == "__main__":
    main(sys.argv[1:])

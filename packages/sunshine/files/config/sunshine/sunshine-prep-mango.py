#!/usr/bin/env python3

"""
Prepare Mango outputs for Sunshine streaming, then restore them on cleanup.

This script is intended to be used via Sunshine's `global_prep_cmd`.

Usage:
  sunshine-prep-mango.py do --width WIDTH --height HEIGHT --fps FPS [--output OUTPUT] [--solo] [--scale SCALE] [--inhibit]
  sunshine-prep-mango.py undo

Notes:
- Requires a running Wayland session where `wlr-randr --json` can see outputs.
- `undo` is intentionally stateless: it re-enables all currently connected
  outputs instead of replaying a saved pre-stream layout.
- Mango's native idle inhibition is surface-driven (idle-inhibit / window rules).
  A Sunshine prep hook has no Mango surface of its own, so `--inhibit` uses
  Noctalia's idle inhibitor directly and tracks ownership in $XDG_RUNTIME_DIR so
  a later `do`/`undo` can recover from a crashed previous run.
- Output restore stays intentionally simple and lossy: `undo` turns connected
  outputs back on, but does not restore prior mode/scale/position/transform.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


INHIBIT_REASON = "sunshine-connection"
INHIBIT_WHO = "sunshine"
TARGET_DPI = 82.0
MIN_SCALE = 1.0
MAX_SCALE = 3.0


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def noctalia_inhibit_pidfile() -> Path:
    return runtime_dir() / "sunshine-mango-noctalia-inhibit.pid"


def noctalia_inhibit_state_file() -> Path:
    return runtime_dir() / "sunshine-mango-noctalia-inhibit.json"


def run_cmd(argv: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _kill_by_pidfile(pidfile: Path, *, timeout: float = 5.0) -> None:
    try:
        pid = int(pidfile.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        pass
    try:
        pidfile.unlink()
    except FileNotFoundError:
        pass


def call_noctalia_idle_inhibitor(action: str) -> bool:
    if not which("qs"):
        return False
    try:
        result = subprocess.run(
            ["qs", "-c", "noctalia-shell", "ipc", "call", "idleInhibitor", action],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def write_noctalia_inhibit_state() -> None:
    noctalia_inhibit_state_file().write_text(
        json.dumps(
            {
                "backend": "noctalia",
                "reason": INHIBIT_REASON,
                "started_at": int(time.time()),
                "pid": os.getpid(),
            }
        ),
        encoding="utf-8",
    )


def has_noctalia_inhibit_state() -> bool:
    return noctalia_inhibit_state_file().exists()


def clear_noctalia_inhibit_state() -> None:
    try:
        noctalia_inhibit_state_file().unlink()
    except FileNotFoundError:
        pass


def kill_runtime_inhibit() -> None:
    if not has_noctalia_inhibit_state():
        return
    try:
        call_noctalia_idle_inhibitor("disable")
    finally:
        clear_noctalia_inhibit_state()


def start_runtime_inhibit() -> None:
    # Mango's native idle inhibition is attached to visible client surfaces.
    # Sunshine's prep hook runs without creating one, so use Noctalia's
    # compositor-adjacent idle inhibitor and track ownership in runtime state.
    kill_runtime_inhibit()
    if call_noctalia_idle_inhibitor("enable"):
        write_noctalia_inhibit_state()


def should_inhibit(inhibit_flag: bool) -> bool:
    v = (os.environ.get("SUNSHINE_INHIBIT") or "").strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return bool(inhibit_flag)


def wlr_randr_json() -> List[Dict[str, Any]]:
    res = run_cmd(["wlr-randr", "--json"], check=True)
    data = json.loads(res.stdout or "[]")
    if not isinstance(data, list):
        raise RuntimeError("Unexpected `wlr-randr --json` reply.")
    return [x for x in data if isinstance(x, dict)]


def stable_output_name(output: Dict[str, Any]) -> str:
    parts = [
        str(output.get("make") or "").strip(),
        str(output.get("model") or "").strip(),
        str(output.get("serial") or "").strip(),
    ]
    return " ".join(p for p in parts if p)


def normalize_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def is_internal_connector(connector: str) -> bool:
    c = (connector or "").lower()
    return c.startswith("edp") or c.startswith("lvds") or c.startswith("dsi")


def find_best_mode(output: Dict[str, Any], width: int, height: int, fps: int) -> Optional[Dict[str, Any]]:
    modes = output.get("modes")
    if not isinstance(modes, list):
        return None

    target_fps = float(fps)
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for mode in modes:
        if not isinstance(mode, dict):
            continue
        try:
            mode_width = int(mode.get("width"))
            mode_height = int(mode.get("height"))
            refresh = float(mode.get("refresh"))
        except Exception:
            continue
        if mode_width != int(width) or mode_height != int(height):
            continue
        candidates.append((abs(refresh - target_fps), mode))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def choose_output(
    outputs: List[Dict[str, Any]],
    *,
    width: int,
    height: int,
    fps: int,
    requested_output: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if requested_output:
        req = normalize_key(requested_output)
        for output in outputs:
            connector = normalize_key(str(output.get("name") or ""))
            stable = normalize_key(stable_output_name(output))
            description = normalize_key(str(output.get("description") or ""))
            if req and req in {connector, stable, description}:
                mode = find_best_mode(output, width, height, fps)
                if mode:
                    return output, mode
                raise RuntimeError(
                    f"Requested output '{requested_output}' has no mode matching {width}x{height}@~{fps}."
                )
        raise RuntimeError(f"Requested output '{requested_output}' not found.")

    scored: List[Tuple[Tuple[int, int, str], Dict[str, Any], Dict[str, Any]]] = []
    for output in outputs:
        connector = str(output.get("name") or "").strip()
        if not connector:
            continue
        mode = find_best_mode(output, width, height, fps)
        if not mode:
            continue
        enabled = bool(output.get("enabled"))
        score = (
            0 if not enabled else 1,
            0 if not is_internal_connector(connector) else 1,
            connector,
        )
        scored.append((score, output, mode))

    if not scored:
        raise RuntimeError(f"No output supports {width}x{height}@~{fps}.")

    scored.sort(key=lambda item: item[0])
    return scored[0][1], scored[0][2]


def compute_dpi(output: Dict[str, Any], *, mode_width: int, mode_height: int) -> Optional[float]:
    physical_size = output.get("physical_size")
    if not isinstance(physical_size, dict):
        return None

    try:
        width_mm = float(physical_size.get("width") or 0)
        height_mm = float(physical_size.get("height") or 0)
        width_px = float(mode_width)
        height_px = float(mode_height)
    except Exception:
        return None

    if width_mm <= 0 or height_mm <= 0 or width_px <= 0 or height_px <= 0:
        return None

    diagonal_inches = math.hypot(width_mm, height_mm) / 25.4
    if diagonal_inches <= 0:
        return None
    return math.hypot(width_px, height_px) / diagonal_inches


def format_scale(scale: float) -> str:
    return f"{round(scale, 2):g}"


def compute_scale(
    scale_arg: Optional[str],
    *,
    output: Dict[str, Any],
    mode_width: int,
    mode_height: int,
) -> Tuple[Optional[str], Optional[str]]:
    if scale_arg is None:
        return None, None

    low = scale_arg.strip().lower()
    if low in {"auto", "heuristic", "client-auto", "dpi-auto"}:
        dpi = compute_dpi(output, mode_width=mode_width, mode_height=mode_height)
        if dpi is not None and TARGET_DPI > 0:
            raw_scale = dpi / TARGET_DPI
            scale = max(MIN_SCALE, min(raw_scale, MAX_SCALE))
            formatted = format_scale(scale)
            return (
                formatted,
                (
                    f"[sunshine-prep-mango] scale mode={low} "
                    f"current_dpi={dpi:.2f} target_dpi={TARGET_DPI:.2f} "
                    f"raw_scale={raw_scale:.4f} applied_scale={formatted}"
                ),
            )

        raw_scale = (mode_height / 1080.0) if mode_height else 1.0
        scale = max(MIN_SCALE, min(raw_scale, MAX_SCALE))
        formatted = format_scale(scale)
        return (
            formatted,
            (
                f"[sunshine-prep-mango] scale mode={low} "
                f"current_dpi=unknown target_dpi={TARGET_DPI:.2f} "
                f"fallback=height/1080 raw_scale={raw_scale:.4f} applied_scale={formatted}"
            ),
        )

    try:
        value = float(scale_arg)
        value = max(MIN_SCALE, min(value, MAX_SCALE))
        formatted = f"{value:g}"
        return (
            formatted,
            f"[sunshine-prep-mango] scale mode=manual requested={scale_arg} applied_scale={formatted}",
        )
    except Exception:
        return (
            None,
            f"[sunshine-prep-mango] scale mode=invalid requested={scale_arg!r} (ignored)",
        )


def format_refresh(refresh: Any) -> str:
    try:
        value = float(refresh)
    except Exception as exc:
        raise RuntimeError(f"Invalid refresh value: {refresh!r}") from exc
    return f"{value:.6f}".rstrip("0").rstrip(".")


def mode_string(mode: Dict[str, Any]) -> str:
    return f"{int(mode['width'])}x{int(mode['height'])}@{format_refresh(mode['refresh'])}Hz"


def apply_output_state(
    name: str,
    *,
    enabled: bool,
    mode: Optional[Dict[str, Any]] = None,
    position: Optional[Dict[str, Any]] = None,
    transform: Optional[str] = None,
    scale: Optional[Any] = None,
) -> None:
    argv = ["wlr-randr", "--output", name]
    if enabled:
        argv.append("--on")
        if mode is not None:
            argv.extend(["--mode", mode_string(mode)])
        if position and "x" in position and "y" in position:
            argv.extend(["--pos", f"{int(position['x'])},{int(position['y'])}"])
        if transform:
            argv.extend(["--transform", str(transform)])
        if scale is not None:
            argv.extend(["--scale", format_scale(float(scale))])
    else:
        argv.append("--off")
    run_cmd(argv, check=True)


def do_action(
    *,
    width: int,
    height: int,
    fps: int,
    output_name: Optional[str],
    solo: bool,
    scale_arg: Optional[str],
    inhibit: bool,
) -> None:
    if not which("wlr-randr"):
        raise RuntimeError("wlr-randr not found in PATH.")

    if which("ydotool"):
        subprocess.run(
            ["ydotool", "mousemove", "-x", "1", "-y", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Clear stale inhibitor ownership from a previous crashed run.
    kill_runtime_inhibit()

    outputs = wlr_randr_json()

    selected_output, selected_mode = choose_output(
        outputs,
        width=width,
        height=height,
        fps=fps,
        requested_output=output_name,
    )
    connector = str(selected_output.get("name") or "").strip()
    if not connector:
        raise RuntimeError("Selected output has no name.")

    scale_to_set, scale_log = compute_scale(
        scale_arg,
        output=selected_output,
        mode_width=int(selected_mode["width"]),
        mode_height=int(selected_mode["height"]),
    )
    if scale_log:
        print(scale_log, file=sys.stderr, flush=True)

    apply_output_state(
        connector,
        enabled=True,
        mode={
            "width": int(selected_mode["width"]),
            "height": int(selected_mode["height"]),
            "refresh": float(selected_mode["refresh"]),
        },
        transform=str(selected_output.get("transform") or "normal"),
        scale=float(scale_to_set) if scale_to_set is not None else None,
    )

    if should_inhibit(inhibit):
        start_runtime_inhibit()

    if solo:
        for output in outputs:
            other = str(output.get("name") or "").strip()
            if not other or other == connector or not bool(output.get("enabled")):
                continue
            apply_output_state(other, enabled=False)


def restore_action() -> None:
    kill_runtime_inhibit()

    if not which("wlr-randr"):
        return

    for output in wlr_randr_json():
        if bool(output.get("enabled")):
            continue
        name = str(output.get("name") or "").strip()
        if not name:
            continue
        apply_output_state(name, enabled=True)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mango output prep for Sunshine")
    sub = parser.add_subparsers(dest="action", help="Action to perform")

    p_do = sub.add_parser("do", help="Select and configure an output for streaming")
    p_do.add_argument("--width", type=int, help="Screen width in pixels")
    p_do.add_argument("--height", type=int, help="Screen height in pixels")
    p_do.add_argument("--fps", type=int, help="Refresh rate in Hz")
    p_do.add_argument(
        "--output",
        type=str,
        help=(
            "Output to use (connector like DP-1, full description from `wlr-randr --json`, "
            "or 'MAKE MODEL SERIAL')"
        ),
    )
    p_do.add_argument(
        "--scale",
        type=str,
        help=(
            "Scale (e.g. 1, 1.25, 1.5), or 'auto'/'heuristic'/'client-auto'/'dpi-auto' "
            "for DPI-based scaling"
        ),
    )
    p_do.add_argument(
        "--solo",
        action="store_true",
        help="Turn off all other outputs during the Sunshine session",
    )
    p_do.add_argument(
        "--inhibit",
        action="store_true",
        help="Renew Noctalia idle inhibitor lease when available, plus systemd-inhibit fallback",
    )

    sub.add_parser("undo", help="Restore outputs from the saved pre-stream snapshot")
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    args = parse_args(argv)
    if not args.action:
        print(__doc__.strip())
        sys.exit(1)

    if args.action == "do":
        width = args.width or int(os.environ.get("SUNSHINE_CLIENT_WIDTH", "0") or 0)
        height = args.height or int(os.environ.get("SUNSHINE_CLIENT_HEIGHT", "0") or 0)
        fps = args.fps or int(os.environ.get("SUNSHINE_CLIENT_FPS", "0") or 0)
        if not (width and height and fps):
            print(
                "ERROR: Missing --width/--height/--fps (or SUNSHINE_CLIENT_* env vars).",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            do_action(
                width=width,
                height=height,
                fps=fps,
                output_name=args.output,
                solo=bool(args.solo),
                scale_arg=args.scale,
                inhibit=bool(getattr(args, "inhibit", False)),
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "undo":
        try:
            restore_action()
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

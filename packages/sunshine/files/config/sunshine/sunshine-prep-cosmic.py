#!/usr/bin/env python3

"""
Prepare COSMIC outputs for Sunshine streaming, then re-enable outputs on cleanup.

This script is intended to be used via Sunshine's `global_prep_cmd`.

Usage:
  sunshine-prep-cosmic.py do --width WIDTH --height HEIGHT --fps FPS [--output OUTPUT] [--solo] [--scale SCALE] [--inhibit]
  sunshine-prep-cosmic.py undo

Notes:
- Requires a running COSMIC session where `cosmic-randr list --kdl` can see outputs.
- `undo` is intentionally stateless: it re-enables all currently disabled
  outputs instead of replaying a saved pre-stream layout.
- Idle prevention uses a tracked `systemd-inhibit --what=idle sleep infinity`
  process while streaming.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


INHIBIT_REASON = "sunshine-connection"
INHIBIT_WHO = "sunshine"
TARGET_DPI = 82.0
MIN_SCALE = 1.0
MAX_SCALE = 3.0
_VALID_TRANSFORMS = {
    "normal",
    "rotate90",
    "rotate180",
    "rotate270",
    "flipped",
    "flipped90",
    "flipped180",
    "flipped270",
}


@dataclass
class Mode:
    width: int
    height: int
    refresh_mhz: int
    current: bool = False
    preferred: bool = False


@dataclass
class Output:
    name: str
    enabled: bool
    make: str = ""
    model: str = ""
    serial_number: str = ""
    physical_width_mm: int = 0
    physical_height_mm: int = 0
    scale: float = 1.0
    transform: Optional[str] = None
    modes: List[Mode] = field(default_factory=list)


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def inhibit_pidfile() -> Path:
    return runtime_dir() / "sunshine-cosmic-systemd-inhibit.pid"


def run_cmd(
    argv: List[str],
    *,
    check: bool = True,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=check,
        input=input_text,
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


def kill_runtime_inhibit() -> None:
    _kill_by_pidfile(inhibit_pidfile())


def start_runtime_inhibit() -> None:
    kill_runtime_inhibit()
    if not which("systemd-inhibit"):
        return
    proc = subprocess.Popen(
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
    inhibit_pidfile().write_text(f"{proc.pid}\n", encoding="utf-8")


def should_inhibit(inhibit_flag: bool) -> bool:
    value = (os.environ.get("SUNSHINE_INHIBIT") or "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return bool(inhibit_flag)


def cosmic_randr_kdl() -> str:
    result = run_cmd(["cosmic-randr", "list", "--kdl"], check=True)
    return result.stdout or ""


def _unescape_kdl_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return value.replace(r'\"', '"').replace(r"\\", "\\")


def _extract_named_strings(line: str) -> Dict[str, str]:
    return {
        key: _unescape_kdl_string(raw)
        for key, raw in re.findall(r'(\w+)="((?:\\.|[^"\\])*)"', line)
    }


def _parse_output_header(line: str) -> Optional[Tuple[str, bool]]:
    match = re.match(
        r'^\s*output\s+"((?:\\.|[^"\\])*)"\s+enabled=#(true|false)\s*\{\s*$',
        line,
    )
    if not match:
        return None
    return _unescape_kdl_string(match.group(1)), match.group(2) == "true"


def parse_cosmic_randr_kdl(text: str) -> List[Output]:
    outputs: List[Output] = []
    current: Optional[Output] = None
    in_modes = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header = _parse_output_header(line)
        if header:
            name, enabled = header
            current = Output(name=name, enabled=enabled)
            outputs.append(current)
            in_modes = False
            continue

        if current is None:
            continue

        if line == "}":
            if in_modes:
                in_modes = False
            else:
                current = None
            continue

        if line.startswith("modes") and line.endswith("{"):
            in_modes = True
            continue

        if in_modes:
            mode_match = re.match(
                r"^mode\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)(?P<flags>.*)$",
                line,
            )
            if not mode_match:
                continue
            current.modes.append(
                Mode(
                    width=int(mode_match.group(1)),
                    height=int(mode_match.group(2)),
                    refresh_mhz=int(mode_match.group(3)),
                    current="current=#true" in mode_match.group("flags"),
                    preferred="preferred=#true" in mode_match.group("flags"),
                )
            )
            continue

        if line.startswith("description"):
            named = _extract_named_strings(line)
            current.make = named.get("make", current.make)
            current.model = named.get("model", current.model)
        elif line.startswith("physical"):
            nums = re.findall(r"-?\d+", line)
            if len(nums) >= 2:
                current.physical_width_mm = int(nums[0])
                current.physical_height_mm = int(nums[1])
        elif line.startswith("scale"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    current.scale = float(parts[1])
                except ValueError:
                    pass
        elif line.startswith("transform"):
            match = re.match(r'^transform\s+"((?:\\.|[^"\\])*)"', line)
            if match:
                current.transform = _unescape_kdl_string(match.group(1))
        elif line.startswith("serial_number"):
            match = re.match(r'^serial_number\s+"((?:\\.|[^"\\])*)"', line)
            if match:
                current.serial_number = _unescape_kdl_string(match.group(1))

    return outputs


def stable_output_name(output: Output) -> str:
    return " ".join(part for part in [output.make, output.model, output.serial_number] if part)


def normalize_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def is_internal_connector(connector: str) -> bool:
    normalized = (connector or "").lower()
    return normalized.startswith("edp") or normalized.startswith("lvds") or normalized.startswith("dsi")


def find_best_mode(output: Output, width: int, height: int, fps: int) -> Optional[Mode]:
    target_refresh_mhz = int(round(float(fps) * 1000.0))
    candidates: List[Tuple[int, Mode]] = []
    for mode in output.modes:
        if mode.width != int(width) or mode.height != int(height):
            continue
        candidates.append((abs(mode.refresh_mhz - target_refresh_mhz), mode))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def choose_output(
    outputs: List[Output],
    *,
    width: int,
    height: int,
    fps: int,
    requested_output: Optional[str],
) -> Tuple[Output, Mode]:
    if requested_output:
        requested = normalize_key(requested_output)
        for output in outputs:
            connector = normalize_key(output.name)
            stable = normalize_key(stable_output_name(output))
            description = normalize_key(" ".join(part for part in [output.make, output.model] if part))
            if requested and requested in {connector, stable, description}:
                mode = find_best_mode(output, width, height, fps)
                if mode:
                    return output, mode
                raise RuntimeError(
                    f"Requested output '{requested_output}' has no mode matching {width}x{height}@~{fps}."
                )
        raise RuntimeError(f"Requested output '{requested_output}' not found.")

    scored: List[Tuple[Tuple[int, int, str], Output, Mode]] = []
    for output in outputs:
        if not output.name:
            continue
        mode = find_best_mode(output, width, height, fps)
        if not mode:
            continue
        score = (
            0 if not output.enabled else 1,
            0 if not is_internal_connector(output.name) else 1,
            output.name,
        )
        scored.append((score, output, mode))

    if not scored:
        raise RuntimeError(f"No COSMIC output supports {width}x{height}@~{fps}.")

    scored.sort(key=lambda item: item[0])
    return scored[0][1], scored[0][2]


def compute_dpi(output: Output, *, mode_width: int, mode_height: int) -> Optional[float]:
    width_mm = float(output.physical_width_mm or 0)
    height_mm = float(output.physical_height_mm or 0)
    width_px = float(mode_width)
    height_px = float(mode_height)

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
    output: Output,
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
                    f"[sunshine-prep-cosmic] scale mode={low} "
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
                f"[sunshine-prep-cosmic] scale mode={low} "
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
            f"[sunshine-prep-cosmic] scale mode=manual requested={scale_arg} applied_scale={formatted}",
        )
    except Exception:
        return (
            None,
            f"[sunshine-prep-cosmic] scale mode=invalid requested={scale_arg!r} (ignored)",
        )


def format_refresh_hz(refresh_mhz: int) -> str:
    return f"{refresh_mhz / 1000.0:.6f}".rstrip("0").rstrip(".")


def apply_output_mode(output: Output, mode: Mode, scale: Optional[str]) -> None:
    argv = [
        "cosmic-randr",
        "mode",
        output.name,
        str(mode.width),
        str(mode.height),
        "--refresh",
        format_refresh_hz(mode.refresh_mhz),
    ]
    if scale is not None:
        argv.extend(["--scale", scale])
    if output.transform in _VALID_TRANSFORMS:
        argv.extend(["--transform", output.transform])
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
    if not which("cosmic-randr"):
        raise RuntimeError("cosmic-randr not found in PATH.")

    if which("ydotool"):
        subprocess.run(
            ["ydotool", "mousemove", "-x", "1", "-y", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    kill_runtime_inhibit()

    outputs = parse_cosmic_randr_kdl(cosmic_randr_kdl())
    if not outputs:
        raise RuntimeError("No COSMIC outputs found from `cosmic-randr list --kdl`.")

    selected_output, selected_mode = choose_output(
        outputs,
        width=width,
        height=height,
        fps=fps,
        requested_output=output_name,
    )

    scale_to_set, scale_log = compute_scale(
        scale_arg,
        output=selected_output,
        mode_width=selected_mode.width,
        mode_height=selected_mode.height,
    )
    if scale_log:
        print(scale_log, file=sys.stderr, flush=True)

    apply_output_mode(selected_output, selected_mode, scale_to_set)

    if should_inhibit(inhibit):
        start_runtime_inhibit()

    if solo:
        for output in outputs:
            if not output.enabled or output.name == selected_output.name:
                continue
            run_cmd(["cosmic-randr", "disable", output.name], check=True)


def restore_action() -> None:
    kill_runtime_inhibit()

    if not which("cosmic-randr"):
        return

    for output in parse_cosmic_randr_kdl(cosmic_randr_kdl()):
        if output.enabled or not output.name:
            continue
        run_cmd(["cosmic-randr", "enable", output.name], check=False)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COSMIC output prep for Sunshine")
    sub = parser.add_subparsers(dest="action", help="Action to perform")

    p_do = sub.add_parser("do", help="Select and configure an output for streaming")
    p_do.add_argument("--width", type=int, help="Screen width in pixels")
    p_do.add_argument("--height", type=int, help="Screen height in pixels")
    p_do.add_argument("--fps", type=int, help="Refresh rate in Hz")
    p_do.add_argument(
        "--output",
        type=str,
        help=(
            "Output to use (connector like DP-1, description from `cosmic-randr list --kdl`, "
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
        help="Prevent idle while the Sunshine session is active",
    )

    sub.add_parser("undo", help="Re-enable currently disabled outputs")
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

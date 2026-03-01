#!/usr/bin/env python3

"""
Prepare Niri outputs for Sunshine streaming, then restore them on cleanup.

This script is intended to be used via Sunshine's `global_prep_cmd`.

Usage:
  sunshine-prep-niri.py do --width WIDTH --height HEIGHT --fps FPS [--output OUTPUT] [--solo] [--scale SCALE]
  sunshine-prep-niri.py undo

Notes:
- Requires a running Niri session and `niri msg` working (typically via $NIRI_SOCKET).
- `undo` does a simple stateless restore by reloading Niri config.
- Optionally uses `systemd-inhibit --what=idle` while active to prevent the session idling (pass `--inhibit`).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


INHIBIT_REASON = "sunshine-connection"
INHIBIT_WHO = "sunshine"


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run_cmd(argv: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def kill_runtime_inhibit() -> None:
    # Best-effort; match other prep scripts.
    subprocess.run(["pkill", "-f", INHIBIT_REASON], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_runtime_inhibit() -> Optional[int]:
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
        return p.pid
    except Exception:
        return None


def should_inhibit(inhibit_flag: bool) -> bool:
    # Opt-in by default. Allow env override for service setups.
    v = (os.environ.get("SUNSHINE_INHIBIT") or "").strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return bool(inhibit_flag)


def parse_niri_json(stdout: str) -> Any:
    data = json.loads(stdout or "null")
    if isinstance(data, dict) and "Err" in data:
        raise RuntimeError(f"niri IPC error: {data['Err']}")
    if isinstance(data, dict) and "Ok" in data:
        return data["Ok"]
    return data


def niri_msg_json(*args: str) -> Any:
    res = run_cmd(["niri", "msg", "--json", *args], check=True)
    return parse_niri_json(res.stdout.strip())


def niri_msg(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_cmd(["niri", "msg", *args], check=check)


def outputs_from_reply(reply: Any) -> List[Dict[str, Any]]:
    if isinstance(reply, dict) and "Outputs" in reply and isinstance(reply["Outputs"], list):
        return reply["Outputs"]
    if isinstance(reply, list):
        return [x for x in reply if isinstance(x, dict)]
    raise RuntimeError(f"Unexpected `niri msg --json outputs` reply: {type(reply)}")


def output_stable_name(o: Dict[str, Any]) -> str:
    make = str(o.get("make") or "").strip()
    model = str(o.get("model") or "").strip()
    serial = str(o.get("serial") or "").strip()
    parts = [p for p in [make, model, serial] if p]
    return " ".join(parts).strip()


def normalize_key(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def is_internal_connector(connector: str) -> bool:
    c = (connector or "").lower()
    return c.startswith("edp") or c.startswith("lvds") or c.startswith("dsi")


def mhz_to_hz_3dp(refresh_mhz: int) -> str:
    hz_int = int(refresh_mhz) // 1000
    frac = int(refresh_mhz) % 1000
    return f"{hz_int}.{frac:03d}"


def compute_scale(scale_arg: Optional[str], height: int) -> Optional[str]:
    """Return a scale argument for `niri msg output ... scale`, or None to skip setting scale.

    Rules:
    - None -> do not change scale.
    - 'auto' -> use Niri's automatic scale selection.
    - 'heuristic' / 'client-auto' -> legacy heuristic: scale = height/1080, clamped to [1.0, 3.0], rounded to 2 decimals.
    - Numeric -> clamp to [1.0, 3.0].
    """
    if scale_arg is None:
        return None

    low = scale_arg.strip().lower()
    if low == "auto":
        return "auto"

    if low in {"heuristic", "client-auto"}:
        s = (height / 1080.0) if height else 1.0
        s = max(1.0, min(s, 3.0))
        return f"{round(s, 2)}"

    try:
        v = float(scale_arg)
        v = max(1.0, min(v, 3.0))
        # Keep stable formatting but avoid trailing zeros obsession.
        return f"{v:g}"
    except Exception:
        return None


def transform_to_config_string(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        v = val.strip()
    else:
        v = str(val).strip()
    if not v:
        return None

    low = v.lower()
    if low in {
        "normal",
        "90",
        "180",
        "270",
        "flipped",
        "flipped-90",
        "flipped-180",
        "flipped-270",
    }:
        return low

    # Common serde enum representations from Rust.
    mapping = {
        "normal": "normal",
        "normal()": "normal",
        "_90": "90",
        "_180": "180",
        "_270": "270",
        "flipped": "flipped",
        "flipped90": "flipped-90",
        "flipped180": "flipped-180",
        "flipped270": "flipped-270",
        "flipped_90": "flipped-90",
        "flipped_180": "flipped-180",
        "flipped_270": "flipped-270",
    }
    return mapping.get(low) or mapping.get(v)  # try exact then lower


def find_best_mode(o: Dict[str, Any], width: int, height: int, fps: int) -> Optional[Dict[str, Any]]:
    modes = o.get("modes")
    if not isinstance(modes, list):
        return None

    target_mhz = int(fps) * 1000
    candidates: List[Tuple[int, Dict[str, Any]]] = []
    for m in modes:
        if not isinstance(m, dict):
            continue
        mw = m.get("width")
        mh = m.get("height")
        rr = m.get("refresh_rate")
        if mw is None or mh is None or rr is None:
            continue
        if int(mw) != int(width) or int(mh) != int(height):
            continue
        delta = abs(int(rr) - target_mhz)
        candidates.append((delta, m))

    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
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
        for o in outputs:
            connector = normalize_key(str(o.get("name") or ""))
            stable = normalize_key(output_stable_name(o))
            if req and (req == connector or req == stable):
                mode = find_best_mode(o, width, height, fps)
                if mode:
                    return o, mode
                raise RuntimeError(
                    f"Requested output '{requested_output}' has no mode matching {width}x{height}@~{fps}."
                )
        raise RuntimeError(f"Requested output '{requested_output}' not found.")

    scored: List[Tuple[Tuple[int, int, str], Dict[str, Any], Dict[str, Any]]] = []
    for o in outputs:
        connector = str(o.get("name") or "")
        if not connector:
            continue
        mode = find_best_mode(o, width, height, fps)
        if not mode:
            continue
        was_on = o.get("current_mode") is not None
        # Prefer an output that is currently off (dummy plug etc), then prefer non-internal.
        score = (
            0 if not was_on else 1,
            0 if not is_internal_connector(connector) else 1,
            connector,
        )
        scored.append((score, o, mode))

    if not scored:
        raise RuntimeError(f"No output supports {width}x{height}@~{fps}.")

    scored.sort(key=lambda t: t[0])
    return scored[0][1], scored[0][2]


def apply_output_mode(output_name: str, *, width: int, height: int, refresh_mhz: int) -> None:
    hz = mhz_to_hz_3dp(refresh_mhz)
    mode_str = f"{width}x{height}@{hz}"
    # Uses the same syntax as the config file.
    niri_msg("output", output_name, "mode", mode_str, check=True)


def apply_output_scale(output_name: str, scale: str) -> None:
    niri_msg("output", output_name, "scale", scale, check=True)


def apply_output_transform(output_name: str, transform: str) -> None:
    niri_msg("output", output_name, "transform", transform, check=True)


def apply_output_position(output_name: str, *, x: int, y: int) -> None:
    niri_msg("output", output_name, "position", f"x={x}", f"y={y}", check=True)


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
    if not which("niri"):
        raise RuntimeError("niri not found in PATH.")

    # tiny wake so remote cursor shows up quickly (optional)
    if which("ydotool"):
        subprocess.run(["ydotool", "mousemove", "-x", "1", "-y", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    outputs = outputs_from_reply(niri_msg_json("outputs"))

    selected_output, selected_mode = choose_output(
        outputs, width=width, height=height, fps=fps, requested_output=output_name
    )
    connector = str(selected_output.get("name") or "").strip()
    if not connector:
        raise RuntimeError("Selected output has no name.")

    # Ensure output is on.
    niri_msg("output", connector, "on", check=True)

    # Set mode.
    rr = int(selected_mode["refresh_rate"])
    apply_output_mode(connector, width=width, height=height, refresh_mhz=rr)

    # Set scale (optional).
    scale_to_set = compute_scale(scale_arg, height)
    if scale_to_set is not None:
        apply_output_scale(connector, scale_to_set)

    if solo:
        for o in outputs:
            other = str(o.get("name") or "").strip()
            if not other or other == connector:
                continue
            if o.get("current_mode") is not None:
                niri_msg("output", other, "off", check=True)

    if should_inhibit(inhibit):
        start_runtime_inhibit()


def try_reload_niri_config() -> bool:
    # Best-effort: Niri's IPC surface may change between versions.
    candidates: List[List[str]] = [
        ["reload-config"],
        ["reload"],
        ["config", "reload"],
    ]
    for args in candidates:
        try:
            niri_msg(*args, check=True)
            return True
        except Exception:
            continue
    return False


def restore_action() -> None:
    if not which("niri"):
        # Still try to cleanup inhibit even if we're not in a niri session.
        kill_runtime_inhibit()
        return

    kill_runtime_inhibit()
    if not try_reload_niri_config():
        raise RuntimeError("Failed to reload Niri config (no stateless restore available).")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Niri output prep for Sunshine")
    sub = parser.add_subparsers(dest="action", help="Action to perform")

    p_do = sub.add_parser("do", help="Select and configure an output for streaming")
    p_do.add_argument("--width", type=int, help="Screen width in pixels")
    p_do.add_argument("--height", type=int, help="Screen height in pixels")
    p_do.add_argument("--fps", type=int, help="Refresh rate in Hz")
    p_do.add_argument(
        "--output",
        type=str,
        help="Output to use (connector like eDP-1, or 'MAKE MODEL SERIAL' from `niri msg outputs`)",
    )
    p_do.add_argument(
        "--scale",
        type=str,
        help="Scale (e.g. 1, 1.25, 1.5), 'auto' (Niri auto), or 'heuristic'/'client-auto' (height-based legacy heuristic)",
    )
    p_do.add_argument(
        "--solo",
        action="store_true",
        help="Turn off all other outputs during the Sunshine session",
    )
    p_do.add_argument(
        "--inhibit",
        action="store_true",
        help="Use systemd-inhibit to prevent idle actions while streaming",
    )

    p_undo = sub.add_parser("undo", help="Restore outputs by reloading Niri config")
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
            print("ERROR: Missing --width/--height/--fps (or SUNSHINE_CLIENT_* env vars).", file=sys.stderr)
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
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "undo":
        try:
            restore_action()
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

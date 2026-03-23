#!/usr/bin/env python3

"""
Prepare Niri outputs for Sunshine streaming, then restore them on cleanup.

This script is intended to be used via Sunshine's `global_prep_cmd`.

Usage:
  sunshine-prep-niri.py do --width WIDTH --height HEIGHT --fps FPS [--output OUTPUT] [--solo] [--scale SCALE] [--autodiscover-socket]
  sunshine-prep-niri.py undo [--autodiscover-socket]

Notes:
- Requires a running Niri session and `niri msg` working (typically via $NIRI_SOCKET).
- `undo` reloads Niri config, then explicitly re-enables any connected outputs
  that are still disabled.
- Optionally uses `systemd-inhibit --what=idle` and Noctalia's idle inhibitor IPC
  while active to prevent the session idling (pass `--inhibit`).
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


INHIBIT_REASON = "sunshine-connection"
INHIBIT_WHO = "sunshine"
ENABLE_NIRI_SOCKET_AUTODISCOVERY = False
TARGET_DPI = 82.0
MIN_SCALE = 1.0
MAX_SCALE = 3.0


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run_cmd(argv: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def set_noctalia_idle_inhibitor(enabled: bool) -> None:
    if not which("qs"):
        return

    action = "enable" if enabled else "disable"
    subprocess.run(
        ["qs", "-c", "noctalia-shell", "ipc", "call", "idleInhibitor", action],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def kill_runtime_inhibit() -> None:
    set_noctalia_idle_inhibitor(False)
    subprocess.run(
        ["pkill", "-f", INHIBIT_REASON],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_runtime_inhibit() -> None:
    kill_runtime_inhibit()
    try:
        subprocess.Popen(
            [
                "systemd-inhibit",
                f"--who={INHIBIT_WHO}",
                "--what=idle:sleep",
                f"--why={INHIBIT_REASON}",
                "--",
                "sleep",
                "infinity",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    set_noctalia_idle_inhibitor(True)


def should_inhibit(inhibit_flag: bool) -> bool:
    # Opt-in by default. Allow env override for service setups.
    v = (os.environ.get("SUNSHINE_INHIBIT") or "").strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return bool(inhibit_flag)


def parse_niri_json(stdout: str) -> Any:
    import json

    data = json.loads(stdout or "null")
    if isinstance(data, dict) and "Err" in data:
        raise RuntimeError(f"niri IPC error: {data['Err']}")
    if isinstance(data, dict) and "Ok" in data:
        return data["Ok"]
    return data


def _is_unix_socket(path: str) -> bool:
    try:
        return stat.S_ISSOCK(os.stat(path).st_mode)
    except OSError:
        return False


def try_autodiscover_niri_socket() -> bool:
    runtime_dir = (
        os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    ).strip()
    if not runtime_dir:
        return False

    runtime_path = Path(runtime_dir)
    if not runtime_path.exists():
        return False

    patterns: List[str] = []
    wayland_display = (os.environ.get("WAYLAND_DISPLAY") or "").strip()
    if wayland_display:
        patterns.append(f"niri.{wayland_display}.*.sock")
    patterns.append("niri.*.sock")

    candidates: List[Path] = []
    for pattern in patterns:
        for path in runtime_path.glob(pattern):
            if _is_unix_socket(str(path)):
                candidates.append(path)

    if not candidates:
        return False

    # Prefer the newest socket in case stale session sockets are still present.
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    os.environ["NIRI_SOCKET"] = str(candidates[0])
    return True


def ensure_niri_socket_env() -> bool:
    current = (os.environ.get("NIRI_SOCKET") or "").strip()
    if current and _is_unix_socket(current):
        return True

    if not ENABLE_NIRI_SOCKET_AUTODISCOVERY:
        return False

    return try_autodiscover_niri_socket()


def niri_msg_json(*args: str) -> Any:
    if not ensure_niri_socket_env():
        raise RuntimeError(
            "NIRI_SOCKET is not set. Set it in the service environment, or pass --autodiscover-socket."
        )
    res = run_cmd(["niri", "msg", "--json", *args], check=True)
    return parse_niri_json(res.stdout.strip())


def niri_msg(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if not ensure_niri_socket_env():
        raise RuntimeError(
            "NIRI_SOCKET is not set. Set it in the service environment, or pass --autodiscover-socket."
        )
    return run_cmd(["niri", "msg", *args], check=check)


def outputs_from_reply(reply: Any) -> List[Dict[str, Any]]:
    if (
        isinstance(reply, dict)
        and "Outputs" in reply
        and isinstance(reply["Outputs"], list)
    ):
        return reply["Outputs"]
    if isinstance(reply, dict):
        # Newer niri versions return outputs as a connector-keyed map.
        out: List[Dict[str, Any]] = []
        for connector, payload in reply.items():
            if not isinstance(payload, dict):
                continue
            entry = dict(payload)
            if not entry.get("name"):
                entry["name"] = str(connector)
            out.append(entry)
        if out:
            return out
    if isinstance(reply, list):
        return [x for x in reply if isinstance(x, dict)]
    raise RuntimeError(f"Unexpected `niri msg --json outputs` reply: {type(reply)}")


def niri_output_config_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return config_home / "niri" / "cfg" / "output.kdl"


def configured_off_output_names() -> Optional[set[str]]:
    path = niri_output_config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    output_names: set[str] = set()
    current_name: Optional[str] = None
    current_explicitly_off = False
    depth = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("/-"):
            continue

        if current_name is None:
            match = re.match(r'^output\s+"([^"]+)"\s*\{', line)
            if match:
                current_name = match.group(1).strip()
                current_explicitly_off = False
                depth = line.count("{") - line.count("}")
                if depth <= 0:
                    if current_explicitly_off:
                        output_names.add(current_name)
                    current_name = None
                    depth = 0
            continue

        if re.match(r"^off(?:\s+true)?(?:\s*//.*)?$", line):
            current_explicitly_off = True

        depth += line.count("{") - line.count("}")
        if depth <= 0:
            if current_name and current_explicitly_off:
                output_names.add(current_name)
            current_name = None
            current_explicitly_off = False
            depth = 0

    return output_names


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


def compute_dpi(
    output: Dict[str, Any],
    *,
    mode_width: int,
    mode_height: int,
) -> Optional[float]:
    physical_size = output.get("physical_size")
    if not (isinstance(physical_size, list) and len(physical_size) >= 2):
        return None

    try:
        width_mm = float(physical_size[0])
        height_mm = float(physical_size[1])
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
    rounded = round(scale, 2)
    return f"{rounded:g}"


def compute_scale(
    scale_arg: Optional[str],
    *,
    output: Dict[str, Any],
    mode_width: int,
    mode_height: int,
) -> Tuple[Optional[str], Optional[str]]:
    """Return a scale argument for `niri msg output ... scale`, or None to skip setting scale.

    Rules:
    - None -> do not change scale.
    - 'auto' -> use Niri's automatic scale selection.
    - 'heuristic' / 'client-auto' / 'dpi-auto' -> DPI-based heuristic:
      scale = current_dpi / TARGET_DPI, clamped to [1.0, 3.0], rounded to 2 decimals.
      If DPI cannot be determined, fall back to height/1080 legacy heuristic.
    - Numeric -> clamp to [1.0, 3.0].
    """
    if scale_arg is None:
        return None, None

    low = scale_arg.strip().lower()
    if low == "auto":
        return "auto", "[sunshine-prep-niri] scale mode=auto (delegating to niri)"

    if low in {"heuristic", "client-auto", "dpi-auto"}:
        dpi = compute_dpi(output, mode_width=mode_width, mode_height=mode_height)
        if dpi is not None and TARGET_DPI > 0:
            raw_scale = dpi / TARGET_DPI
            scale = max(MIN_SCALE, min(raw_scale, MAX_SCALE))
            formatted = format_scale(scale)
            return (
                formatted,
                (
                    f"[sunshine-prep-niri] scale mode={low} "
                    f"current_dpi={dpi:.2f} target_dpi={TARGET_DPI:.2f} "
                    f"raw_scale={raw_scale:.4f} applied_scale={formatted}"
                ),
            )
        else:
            # Fallback for missing or invalid EDID physical size.
            raw_scale = (mode_height / 1080.0) if mode_height else 1.0
            scale = max(MIN_SCALE, min(raw_scale, MAX_SCALE))
            formatted = format_scale(scale)
            return (
                formatted,
                (
                    f"[sunshine-prep-niri] scale mode={low} "
                    f"current_dpi=unknown target_dpi={TARGET_DPI:.2f} "
                    f"fallback=height/1080 raw_scale={raw_scale:.4f} applied_scale={formatted}"
                ),
            )

    try:
        v = float(scale_arg)
        v = max(MIN_SCALE, min(v, MAX_SCALE))
        # Keep stable formatting but avoid trailing zeros obsession.
        formatted = f"{v:g}"
        return (
            formatted,
            f"[sunshine-prep-niri] scale mode=manual requested={scale_arg} applied_scale={formatted}",
        )
    except Exception:
        return (
            None,
            f"[sunshine-prep-niri] scale mode=invalid requested={scale_arg!r} (ignored)",
        )


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


def find_best_mode(
    o: Dict[str, Any], width: int, height: int, fps: int
) -> Optional[Dict[str, Any]]:
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


def apply_output_mode(
    output_name: str, *, width: int, height: int, refresh_mhz: int
) -> None:
    hz = mhz_to_hz_3dp(refresh_mhz)
    mode_str = f"{width}x{height}@{hz}"
    # Uses the same syntax as the config file.
    niri_msg("output", output_name, "mode", mode_str, check=True)


def apply_output_scale(output_name: str, scale: str) -> None:
    niri_msg("output", output_name, "scale", scale, check=True)


def apply_output_transform(output_name: str, transform: str) -> None:
    niri_msg("output", output_name, "transform", transform, check=True)


def apply_output_position(output_name: str, *, x: int, y: int) -> None:
    niri_msg("output", output_name, "position", "set", str(x), str(y), check=True)


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
        subprocess.run(
            ["ydotool", "mousemove", "-x", "1", "-y", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

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
    scale_to_set, scale_log = compute_scale(
        scale_arg,
        output=selected_output,
        mode_width=int(selected_mode["width"]),
        mode_height=int(selected_mode["height"]),
    )
    if scale_log:
        print(scale_log, file=sys.stderr, flush=True)
    if scale_to_set is not None:
        apply_output_scale(connector, scale_to_set)

    if should_inhibit(inhibit):
        start_runtime_inhibit()

    if solo:
        for o in outputs:
            other = str(o.get("name") or "").strip()
            if not other or other == connector:
                continue
            if o.get("current_mode") is not None:
                niri_msg("output", other, "off", check=True)


def try_reload_niri_config() -> bool:
    # Best-effort: Niri's IPC surface may change between versions.
    candidates: List[List[str]] = [
        ["action", "load-config-file"],
    ]
    for args in candidates:
        try:
            niri_msg(*args, check=True)
            return True
        except Exception:
            continue
    return False


def reenable_disabled_outputs() -> None:
    off_names = configured_off_output_names()
    outputs = outputs_from_reply(niri_msg_json("outputs"))
    for output in outputs:
        connector = str(output.get("name") or "").strip()
        if not connector:
            continue
        if output.get("current_mode") is not None:
            continue
        stable_name = output_stable_name(output)
        if off_names is not None:
            if connector in off_names or stable_name in off_names:
                continue
        niri_msg("output", connector, "on", check=True)


def restore_action() -> None:
    if not which("niri"):
        # Still try to cleanup inhibit even if we're not in a niri session.
        kill_runtime_inhibit()
        return

    kill_runtime_inhibit()
    # if not try_reload_niri_config():
    #     raise RuntimeError("Failed to reload Niri config (no stateless restore available).")
    reenable_disabled_outputs()


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
        help=(
            "Scale (e.g. 1, 1.25, 1.5), 'auto' (Niri auto), or "
            "'heuristic'/'client-auto'/'dpi-auto' (DPI-based: current_dpi/82)"
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
        help="Use systemd-inhibit plus `qs -c noctalia-shell ipc call idleInhibitor ...`",
    )
    p_do.add_argument(
        "--autodiscover-socket",
        action="store_true",
        help="If NIRI_SOCKET is missing, auto-discover the niri IPC socket in XDG_RUNTIME_DIR",
    )

    p_undo = sub.add_parser("undo", help="Restore outputs by reloading Niri config")
    p_undo.add_argument(
        "--autodiscover-socket",
        action="store_true",
        help="If NIRI_SOCKET is missing, auto-discover the niri IPC socket in XDG_RUNTIME_DIR",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    global ENABLE_NIRI_SOCKET_AUTODISCOVERY
    args = parse_args(argv)
    if not args.action:
        print(__doc__.strip())
        sys.exit(1)
    ENABLE_NIRI_SOCKET_AUTODISCOVERY = bool(getattr(args, "autodiscover_socket", False))

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

#!/usr/bin/env python3

"""
Prepare Niri outputs for Sunshine streaming, then restore them on cleanup.

This script is intended to be used via Sunshine's `global_prep_cmd`.

Usage:
  sunshine-prep-niri.py do --width WIDTH --height HEIGHT --fps FPS [--output OUTPUT] [--headless] [--solo] [--scale SCALE] [--suspend-niri-shell] [--autodiscover-socket]
  sunshine-prep-niri.py undo [--dormant-headless] [--suspend-niri-shell] [--autodiscover-socket]

Notes:
- Requires a running Niri session and `niri msg` working (typically via $NIRI_SOCKET).
- `undo` re-enables disabled outputs except configured-off outputs, then turns
  the fixed Sunshine virtual output off unless `--dormant-headless` is passed.
- Optionally inhibits idle via Noctalia's idle inhibitor IPC (pass `--inhibit`).
  Rendered Niri config leaves this off because WLR/headless capture does not
  need the KMS-only DPMS error-spam workaround.
- Optionally stops `niri-shell.service` around output changes and restarts it
  before Sunshine connects / after undo (pass `--suspend-niri-shell`).
"""

from __future__ import annotations

import argparse
import functools
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


INHIBIT_REASON = "sunshine-connection"
INHIBIT_WHO = "sunshine"
ENABLE_NIRI_SOCKET_AUTODISCOVERY = False
TARGET_DPI = 82.0
MIN_SCALE = 1.0
MAX_SCALE = 3.0
HEADLESS_OUTPUT_NAME = "sunshine"
DORMANT_OUTPUT_FPS = "60.000"
DEFAULT_NIRI_SHELL_SERVICE = "niri-shell.service"
NIRI_SHELL_SERVICE_ENV_VAR_NAME = "NIRI_SHELL_SERVICE"
# Dotman can render vars.niri.bin into this env var so prep uses the same
# local Niri build as niri.service instead of an older system PATH binary.
NIRI_BIN_ENV_VAR_NAME = "NIRI_BIN"


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def expand_niri_bin(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw))


@functools.cache
def niri_bin() -> str:
    configured = (os.environ.get(NIRI_BIN_ENV_VAR_NAME) or "").strip()
    if configured:
        return expand_niri_bin(configured)
    return "niri"


def command_exists(command: str) -> bool:
    if os.sep in command:
        return os.access(command, os.X_OK)
    return which(command)


def require_niri_bin() -> str:
    command = niri_bin()
    if command_exists(command):
        return command
    if os.environ.get(NIRI_BIN_ENV_VAR_NAME):
        raise RuntimeError(f"{command} from ${NIRI_BIN_ENV_VAR_NAME} is not executable.")
    raise RuntimeError("niri not found in PATH.")


def has_niri_bin() -> bool:
    return command_exists(niri_bin())


def run_cmd(argv: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def niri_shell_service_name() -> str:
    return (os.environ.get(NIRI_SHELL_SERVICE_ENV_VAR_NAME) or DEFAULT_NIRI_SHELL_SERVICE).strip()


def _niri_shell_suspend_state_file() -> Path:
    return runtime_dir() / "sunshine-niri-shell-suspended.service"


def _systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def user_service_is_active(service: str) -> bool:
    if not which("systemctl"):
        return False
    result = _systemctl_user("is-active", service)
    return result.returncode == 0 and result.stdout.strip() in {"active", "activating", "reloading"}


def suspend_niri_shell_if_active() -> bool:
    """Stop Noctalia/niri-shell before output hotplug churn so it cannot process stale wl_output events."""
    if not which("systemctl"):
        return False

    service = niri_shell_service_name()
    state_file = _niri_shell_suspend_state_file()
    if state_file.exists():
        return True
    if not user_service_is_active(service):
        return False

    result = _systemctl_user("stop", service)
    if result.returncode != 0:
        print(
            f"[sunshine-prep-niri] warning: failed to stop {service}: {result.stderr.strip()}",
            file=sys.stderr,
            flush=True,
        )
        return False

    state_file.write_text(service + "\n", encoding="utf-8")
    print(f"[sunshine-prep-niri] stopped {service} during output reconfiguration", file=sys.stderr, flush=True)
    return True


def resume_suspended_niri_shell() -> bool:
    state_file = _niri_shell_suspend_state_file()
    try:
        service = state_file.read_text(encoding="utf-8").strip() or DEFAULT_NIRI_SHELL_SERVICE
    except OSError:
        return False

    if not which("systemctl"):
        return False

    reset_result = _systemctl_user("reset-failed", service)
    if reset_result.returncode != 0:
        print(
            f"[sunshine-prep-niri] warning: failed to reset-failed {service}: {reset_result.stderr.strip()}",
            file=sys.stderr,
            flush=True,
        )
        return False

    result = _systemctl_user("start", service)
    if result.returncode != 0:
        print(
            f"[sunshine-prep-niri] warning: failed to start {service}: {result.stderr.strip()}",
            file=sys.stderr,
            flush=True,
        )
        return False

    try:
        state_file.unlink()
    except FileNotFoundError:
        pass
    print(f"[sunshine-prep-niri] started {service} after output reconfiguration", file=sys.stderr, flush=True)
    return True


def _screensaver_inhibit_pidfile() -> Path:
    return runtime_dir() / "sunshine-screensaver-inhibit.pid"



def _kill_by_pidfile(pidfile: Path, *, timeout: float = 5.0) -> None:
    try:
        pid = int(pidfile.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        # Wait for the process to exit so its cleanup handler (e.g. D-Bus
        # UnInhibit) has time to complete before we proceed.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)  # probe — raises if gone
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            # Still alive after timeout — force kill.
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


def cleanup_legacy_inhibitors() -> None:
    # Clean up stale inhibitors from the previous D-Bus/systemd implementation.
    _kill_by_pidfile(_screensaver_inhibit_pidfile())
    subprocess.run(
        ["pkill", "-f", INHIBIT_REASON],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def kill_runtime_inhibit() -> None:
    set_noctalia_idle_inhibitor(False)
    cleanup_legacy_inhibitors()



def set_noctalia_idle_inhibitor(enabled: bool) -> bool:
    if not which("qs"):
        return False
    action = "enable" if enabled else "disable"
    result = subprocess.run(
        ["qs", "-c", "noctalia-shell", "ipc", "call", "idleInhibitor", action],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def start_runtime_inhibit() -> None:
    # Keep Niri path simple: Noctalia exposes a global idle-inhibitor toggle,
    # so Sunshine turns it on at stream start and off at stream end.
    cleanup_legacy_inhibitors()
    set_noctalia_idle_inhibitor(True)


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
    res = run_cmd([require_niri_bin(), "msg", "--json", *args], check=True)
    return parse_niri_json(res.stdout.strip())


def niri_msg(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if not ensure_niri_socket_env():
        raise RuntimeError(
            "NIRI_SOCKET is not set. Set it in the service environment, or pass --autodiscover-socket."
        )
    return run_cmd([require_niri_bin(), "msg", *args], check=check)


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


def output_block_line_has_off_directive(line: str) -> bool:
    # Lightweight KDL scan only: enough for repo output.kdl, not a full parser.
    # Strip inline comments so commented `off` does not preserve outputs as off.
    uncommented = line.split("//", 1)[0].strip()
    return re.search(r"(?:^|[{\s;])off(?:\s+true)?\s*(?=$|[};])", uncommented) is not None


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
            if not match:
                continue
            current_name = match.group(1).strip()
            current_explicitly_off = False

        if output_block_line_has_off_directive(line):
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



def find_output_by_name(outputs: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    wanted = normalize_key(name)
    for output in outputs:
        connector = normalize_key(str(output.get("name") or ""))
        stable = normalize_key(output_stable_name(output))
        if wanted and (wanted == connector or wanted == stable):
            return output
    return None


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


def apply_output_custom_mode(output_name: str, *, width: int, height: int, fps: Any) -> None:
    mode_str = f"{width}x{height}@{str(fps).strip()}"
    niri_msg("output", output_name, "custom-mode", mode_str, check=True)


def ensure_headless_output(*, name: str, width: int, height: int, fps: int) -> None:
    outputs = outputs_from_reply(niri_msg_json("outputs"))
    if find_output_by_name(outputs, name) is not None:
        niri_msg("output", name, "on", check=True)
        apply_output_custom_mode(name, width=width, height=height, fps=fps)
        return

    try:
        niri_msg(
            "create-virtual-output",
            "--name",
            name,
            "--width",
            str(width),
            "--height",
            str(height),
            "--refresh-rate",
            str(int(fps)),
            check=True,
        )
    except Exception as exc:
        raise RuntimeError(
            "Failed to create Niri headless output. Install a Niri build with "
            "`niri msg create-virtual-output` support."
        ) from exc



def apply_output_scale(output_name: str, scale: str) -> None:
    niri_msg("output", output_name, "scale", scale, check=True)


def current_mode_dimensions(output: Optional[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
    if not output:
        return None
    current_mode = output.get("current_mode")
    if not isinstance(current_mode, dict):
        return None
    try:
        width = int(current_mode["width"])
        height = int(current_mode["height"])
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height



def do_action(
    *,
    width: int,
    height: int,
    fps: int,
    output_name: Optional[str],
    headless: bool,
    solo: bool,
    scale_arg: Optional[str],
    inhibit: bool,
    suspend_niri_shell: bool,
) -> None:
    require_niri_bin()

    niri_shell_suspended = False
    if suspend_niri_shell:
        niri_shell_suspended = suspend_niri_shell_if_active()

    try:
        do_output_action(
            width=width,
            height=height,
            fps=fps,
            output_name=output_name,
            headless=headless,
            solo=solo,
            scale_arg=scale_arg,
            inhibit=inhibit,
        )
    finally:
        if niri_shell_suspended:
            resume_suspended_niri_shell()


def do_output_action(
    *,
    width: int,
    height: int,
    fps: int,
    output_name: Optional[str],
    headless: bool,
    solo: bool,
    scale_arg: Optional[str],
    inhibit: bool,
) -> None:
    # tiny wake so remote cursor shows up quickly (optional)
    if which("ydotool"):
        subprocess.run(
            ["ydotool", "mousemove", "-x", "1", "-y", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if headless:
        if output_name:
            raise RuntimeError("Do not pass --output with --headless; the headless output name is fixed.")
        ensure_headless_output(name=HEADLESS_OUTPUT_NAME, width=width, height=height, fps=fps)
        outputs = outputs_from_reply(niri_msg_json("outputs"))
        selected_output = find_output_by_name(outputs, HEADLESS_OUTPUT_NAME)
        if selected_output is None:
            raise RuntimeError(f"Created headless output '{HEADLESS_OUTPUT_NAME}' was not found in niri outputs.")
        selected_mode = {"width": width, "height": height, "refresh_rate": int(fps) * 1000}
    else:
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
    if headless:
        apply_output_custom_mode(connector, width=width, height=height, fps=fps)
    else:
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

    if solo:
        # Move focus before removing the previous output so Niri does not need
        # to migrate focus while Wayland clients process monitor removal.
        niri_msg("action", "focus-monitor", connector, check=True)
        for o in outputs:
            other = str(o.get("name") or "").strip()
            if not other or other == connector:
                continue
            if o.get("current_mode") is not None:
                niri_msg("output", other, "off", check=True)

    # Noctalia may show/update an idle-inhibitor notification. Do this after
    # solo output changes so Qt/QML clients do not keep notification surfaces on
    # outputs that are about to be removed.
    if inhibit:
        start_runtime_inhibit()


def park_headless_output_dormant() -> None:
    # Keep wl_output present. `niri msg output sunshine off` hot-removes it,
    # which can crash clients that still hold output/screen state.
    niri_msg("output", HEADLESS_OUTPUT_NAME, "on", check=False)

    outputs = outputs_from_reply(niri_msg_json("outputs"))
    dimensions = current_mode_dimensions(find_output_by_name(outputs, HEADLESS_OUTPUT_NAME))
    if dimensions is not None:
        width, height = dimensions
        apply_output_custom_mode(
            HEADLESS_OUTPUT_NAME,
            width=width,
            height=height,
            fps=DORMANT_OUTPUT_FPS,
        )
    else:
        print(
            f"[sunshine-prep-niri] dormant fps skipped: {HEADLESS_OUTPUT_NAME} current resolution unknown",
            file=sys.stderr,
            flush=True,
        )


def disable_headless_output() -> None:
    niri_msg("output", HEADLESS_OUTPUT_NAME, "off", check=False)


def reenable_disabled_outputs() -> None:
    off_names = configured_off_output_names()
    outputs = outputs_from_reply(niri_msg_json("outputs"))
    for output in outputs:
        connector = str(output.get("name") or "").strip()
        if not connector:
            continue
        # Niri config reload can preserve transient IPC state, so undo must
        # explicitly skip and later disable the Sunshine virtual output instead
        # of trusting `output "sunshine" { off }` in config to win.
        if connector == HEADLESS_OUTPUT_NAME:
            continue
        if output.get("current_mode") is not None:
            continue
        stable_name = output_stable_name(output)
        if off_names is not None:
            if connector in off_names or stable_name in off_names:
                continue
        niri_msg("output", connector, "on", check=True)


def restore_action(*, dormant_headless: bool, suspend_niri_shell: bool) -> None:
    if not has_niri_bin():
        # Still try to cleanup inhibit/shell state even if we're not in a niri session.
        kill_runtime_inhibit()
        resume_suspended_niri_shell()
        return

    if suspend_niri_shell:
        suspend_niri_shell_if_active()

    try:
        # Avoid config reload here. Niri may keep transient IPC output changes
        # across `load-config-file` when disk `outputs` are unchanged, leaving
        # the Sunshine virtual output on after stream teardown.
        reenable_disabled_outputs()
        if dormant_headless:
            park_headless_output_dormant()
        else:
            disable_headless_output()
    finally:
        kill_runtime_inhibit()
        resume_suspended_niri_shell()


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
        "--headless",
        action="store_true",
        help="Create/use a fixed-name Niri headless output for this stream",
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
        help="Inhibit idle via Noctalia idle inhibitor IPC",
    )
    p_do.add_argument(
        "--suspend-niri-shell",
        action="store_true",
        help="Stop niri-shell.service during output changes and restart it before streaming/after undo",
    )
    p_do.add_argument(
        "--autodiscover-socket",
        action="store_true",
        help="If NIRI_SOCKET is missing, auto-discover the niri IPC socket in XDG_RUNTIME_DIR",
    )

    p_undo = sub.add_parser(
        "undo", help="Manually re-enable non-Sunshine outputs and disable Sunshine headless"
    )
    p_undo.add_argument(
        "--dormant-headless",
        action="store_true",
        help="Park the Sunshine headless output in low-power dormant mode instead of turning it off",
    )
    p_undo.add_argument(
        "--suspend-niri-shell",
        action="store_true",
        help="Stop niri-shell.service during output changes and restart it after undo",
    )
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
                headless=bool(getattr(args, "headless", False)),
                solo=bool(args.solo),
                scale_arg=args.scale,
                inhibit=bool(getattr(args, "inhibit", False)),
                suspend_niri_shell=bool(getattr(args, "suspend_niri_shell", False)),
            )
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "undo":
        try:
            restore_action(
                dormant_headless=bool(getattr(args, "dormant_headless", False)),
                suspend_niri_shell=bool(getattr(args, "suspend_niri_shell", False)),
            )
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

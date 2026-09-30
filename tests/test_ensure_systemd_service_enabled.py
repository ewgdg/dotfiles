from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/ensure_systemd_service_enabled.sh"

# Fake user systemctl: the unit is enabled, binds to $FAKE_BINDS_TO, and each bound unit is
# active only when listed in $FAKE_ACTIVE_UNITS. Every call is appended to $FAKE_LOG.
FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
args=" $* "
case "$args" in
  *" daemon-reload "*) exit 0 ;;
  *" is-enabled "*) exit 0 ;;
  *" --property=BindsTo "*) echo "$FAKE_BINDS_TO"; exit 0 ;;
  *" is-active "*)
    for unit in $FAKE_ACTIVE_UNITS; do
      [ "$unit" = "${@: -1}" ] && exit 0
    done
    exit 3 ;;
  *" start "*) exit 0 ;;
esac
exit 0
"""


def run_ensure(tmp_path: Path, *, binds_to: str, active_units: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "systemctl"
    fake.write_text(FAKE_SYSTEMCTL)
    fake.chmod(0o755)
    log = tmp_path / "systemctl.log"
    log.touch()

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "FAKE_BINDS_TO": binds_to,
        "FAKE_ACTIVE_UNITS": active_units,
    }
    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "user", "niri-shell.service"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed, log.read_text().splitlines()


def started(calls: list[str]) -> bool:
    return "--user start niri-shell.service" in calls


def test_does_not_start_unit_bound_to_an_inactive_unit(tmp_path: Path) -> None:
    # Starting it would pull niri.service in under another compositor's session.
    completed, calls = run_ensure(tmp_path, binds_to="niri.service", active_units="")

    assert completed.returncode == 0
    assert not started(calls)
    assert "niri.service" in completed.stderr


def test_starts_unit_when_its_bound_unit_is_active(tmp_path: Path) -> None:
    completed, calls = run_ensure(tmp_path, binds_to="niri.service", active_units="niri.service")

    assert completed.returncode == 0
    assert started(calls)


def test_starts_unit_without_bindings(tmp_path: Path) -> None:
    completed, calls = run_ensure(tmp_path, binds_to="", active_units="")

    assert completed.returncode == 0
    assert started(calls)

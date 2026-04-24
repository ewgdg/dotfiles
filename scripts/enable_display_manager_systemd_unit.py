#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterable, Sequence


_DEFAULT_UNIT_DIRS = (
    Path("/etc/systemd/system"),
    Path("/run/systemd/system"),
    Path("/usr/local/lib/systemd/system"),
    Path("/usr/lib/systemd/system"),
    Path("/lib/systemd/system"),
)
_DISPLAY_MANAGER_ALIAS = "display-manager.service"


def extract_aliases_from_unit_text(unit_text: str) -> set[str]:
    aliases: set[str] = set()

    for raw_line in unit_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if not line.startswith("Alias="):
            continue
        aliases.update(alias for alias in line.removeprefix("Alias=").split() if alias)

    return aliases


def iter_effective_service_units(unit_dirs: Sequence[Path]) -> Iterable[Path]:
    seen_names: set[str] = set()

    for unit_dir in unit_dirs:
        if not unit_dir.is_dir():
            continue
        for unit_path in sorted(unit_dir.glob("*.service")):
            if unit_path.name in seen_names:
                continue
            seen_names.add(unit_path.name)
            yield unit_path


def unit_defines_display_manager_alias(unit_path: Path) -> bool:
    aliases = extract_aliases_from_unit_text(unit_path.read_text(encoding="utf-8"))
    return _DISPLAY_MANAGER_ALIAS in aliases


def find_display_manager_units(unit_dirs: Sequence[Path]) -> tuple[str, ...]:
    unit_names: list[str] = []

    for unit_path in iter_effective_service_units(unit_dirs):
        if unit_defines_display_manager_alias(unit_path):
            unit_names.append(unit_path.name)

    return tuple(unit_names)


def systemctl_is_enabled(unit_name: str) -> bool:
    completed = subprocess.run(
        ["systemctl", "--quiet", "is-enabled", unit_name],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def select_units_to_disable(
    *,
    display_manager_units: Sequence[str],
    keep_unit: str,
    is_enabled: Callable[[str], bool],
) -> tuple[str, ...]:
    return tuple(
        unit_name
        for unit_name in display_manager_units
        if unit_name != keep_unit and is_enabled(unit_name)
    )


def should_enable_unit(unit_name: str, *, is_enabled: Callable[[str], bool]) -> bool:
    return not is_enabled(unit_name)


def systemctl_unit_available(unit_name: str) -> bool:
    completed = subprocess.run(
        ["systemctl", "show", "--property=FragmentPath", "--value", unit_name],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and bool(completed.stdout.strip())


def run_systemctl_mutation(args: Sequence[str]) -> int:
    command = ["systemctl", *args]
    if os.geteuid() != 0:
        # Intentionally use plain sudo. Repo policy does not assume askpass is configured.
        command = ["sudo", *command]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def daemon_reload() -> bool:
    return run_systemctl_mutation(["daemon-reload"]) == 0


def print_dry_run_plan(*, target_unit: str, enable_target: bool, units_to_disable: Sequence[str]) -> int:
    if enable_target:
        print(f"enable {target_unit}")
    for unit_name in units_to_disable:
        print(f"disable --now {unit_name}")
    return 0


def enable_display_manager_unit(
    *,
    target_unit: str,
    unit_dirs: Sequence[Path],
    dry_run: bool,
) -> int:
    if not daemon_reload():
        print(f"Skipping {target_unit}: systemd is not reachable.", file=sys.stderr)
        return 0

    if not systemctl_unit_available(target_unit):
        print(f"Skipping {target_unit}: the system unit is not available.", file=sys.stderr)
        return 0

    display_manager_units = find_display_manager_units(unit_dirs)
    enable_target = should_enable_unit(target_unit, is_enabled=systemctl_is_enabled)
    units_to_disable = select_units_to_disable(
        display_manager_units=display_manager_units,
        keep_unit=target_unit,
        is_enabled=systemctl_is_enabled,
    )

    if dry_run:
        return print_dry_run_plan(
            target_unit=target_unit,
            enable_target=enable_target,
            units_to_disable=units_to_disable,
        )

    if enable_target and run_systemctl_mutation(["enable", target_unit]) != 0:
        return 1

    if units_to_disable and run_systemctl_mutation(["disable", "--now", *units_to_disable]) != 0:
        return 1

    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable one display-manager unit and disable other enabled display managers."
    )
    parser.add_argument("unit_name", help="Display-manager unit to keep enabled.")
    parser.add_argument(
        "--unit-dir",
        action="append",
        dest="unit_dirs",
        type=Path,
        help="Additional systemd unit directory list for discovery. Overrides defaults when passed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions that would be taken and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    unit_dirs = tuple(args.unit_dirs or _DEFAULT_UNIT_DIRS)

    try:
        return enable_display_manager_unit(
            target_unit=args.unit_name,
            unit_dirs=unit_dirs,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"enable_display_manager_systemd_unit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

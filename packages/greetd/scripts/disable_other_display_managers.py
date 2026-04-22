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


def sudo_prefix() -> list[str]:
    if sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty():
        return ["sudo"]
    return ["sudo", "-A"]


def disable_units(unit_names: Sequence[str], *, dry_run: bool) -> int:
    if not unit_names:
        return 0

    if dry_run:
        sys.stdout.write("\n".join(unit_names) + "\n")
        return 0

    command = ["systemctl", "disable", "--now", *unit_names]
    if os.geteuid() != 0:
        command = [*sudo_prefix(), *command]

    completed = subprocess.run(command, check=False)
    return completed.returncode


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Disable enabled display-manager services other than the one to keep."
    )
    parser.add_argument(
        "--keep-unit",
        default="greetd.service",
        help="Display-manager unit to keep enabled. Default: greetd.service",
    )
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
        help="Print units that would be disabled and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    unit_dirs = tuple(args.unit_dirs or _DEFAULT_UNIT_DIRS)

    try:
        display_manager_units = find_display_manager_units(unit_dirs)
        units_to_disable = select_units_to_disable(
            display_manager_units=display_manager_units,
            keep_unit=args.keep_unit,
            is_enabled=systemctl_is_enabled,
        )
    except Exception as exc:
        print(f"disable_other_display_managers: {exc}", file=sys.stderr)
        return 1

    return disable_units(units_to_disable, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

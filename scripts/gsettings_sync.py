#!/usr/bin/env python3
"""
gsettings_sync.py - Sync GNOME gsettings with repo-managed INI files.

dump mode (trans_update):
  Reads current values from gsettings for every schema/key listed in
  --template-file, then writes them to the output path.
  The base_path argument ({0}) is ignored.

apply mode (action):
  Reads the repo INI file (base_path, {0}) and applies each key via
  `gsettings set`.
"""

from __future__ import annotations

import argparse
import configparser
import shutil
import subprocess
import sys
from pathlib import Path


def gsettings_get(schema: str, key: str) -> str | None:
    result = subprocess.run(
        ["gsettings", "get", schema, key],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def gsettings_set(schema: str, key: str, value: str) -> None:
    subprocess.run(
        ["gsettings", "set", schema, key, value],
        check=True,
    )


def read_ini(path: Path) -> configparser.RawConfigParser:
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    if path.exists():
        parser.read(path, encoding="utf-8")
    return parser


def write_ini(parser: configparser.RawConfigParser, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


_FULL_SCHEMA_SUFFIX = ".*"


def resolve_schema_name(section_name: str) -> str:
    if section_name.endswith(_FULL_SCHEMA_SUFFIX):
        return section_name[: -len(_FULL_SCHEMA_SUFFIX)]
    return section_name


def gsettings_list_keys(schema: str) -> list[str]:
    result = subprocess.run(
        ["gsettings", "list-keys", schema],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return sorted(result.stdout.splitlines())


def iter_template_keys(template: configparser.RawConfigParser, section_name: str) -> list[str]:
    if section_name.endswith(_FULL_SCHEMA_SUFFIX):
        return gsettings_list_keys(resolve_schema_name(section_name))
    return list(template.options(section_name))


def run_dump(template_path: Path, output_path: Path) -> None:
    """Read current gsettings values and write them to output_path."""
    template = read_ini(template_path)
    output = configparser.RawConfigParser()
    output.optionxform = str

    for section_name in template.sections():
        schema = resolve_schema_name(section_name)
        keys = iter_template_keys(template, section_name)

        output.add_section(section_name)
        for key in keys:
            value = gsettings_get(schema, key)
            if value is None:
                print(
                    f"warning: gsettings get {schema} {key} failed; skipping",
                    file=sys.stderr,
                )
                continue
            output.set(section_name, key, value)

    write_ini(output, output_path)


def run_apply(input_path: Path) -> None:
    """Apply repo INI values to gsettings."""
    parser = read_ini(input_path)

    for section_name in parser.sections():
        schema = resolve_schema_name(section_name)
        for key, value in parser.items(section_name):
            gsettings_set(schema, key, value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync gsettings values with repo-managed INI files."
    )
    parser.add_argument(
        "base_path",
        type=Path,
        help="Input file ({0} for dump, {1} for apply).",
    )
    parser.add_argument("--mode", choices=["dump", "apply"], required=True)
    parser.add_argument(
        "output_path",
        type=Path,
        nargs="?",
        default=None,
        help="Output file ({1}). Required for dump mode.",
    )
    parser.add_argument(
        "--template-file",
        type=Path,
        default=None,
        help="(dump mode) INI file listing schemas/keys to read from gsettings. "
        "Defaults to base_path when not provided.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if shutil.which("gsettings") is None:
        print("gsettings not found; skipping gsettings sync", file=sys.stderr)
        return 0

    if args.mode == "dump":
        if args.output_path is None:
            print("error: output_path is required for dump mode", file=sys.stderr)
            return 2
        template_path = args.template_file if args.template_file is not None else args.base_path
        if not template_path.exists():
            print(
                f"template file not found: {template_path}; skipping gsettings dump",
                file=sys.stderr,
            )
            return 0
        run_dump(template_path, args.output_path)
        return 0

    if not args.base_path.exists():
        print(
            f"dotfile not found: {args.base_path}; skipping gsettings apply",
            file=sys.stderr,
        )
        return 0
    run_apply(args.base_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

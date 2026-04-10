#!/usr/bin/env python3
"""
gsettings_sync.py - Sync GNOME gsettings with repo-managed INI files.

dump mode (trans_update):
  Reads the current GSettings user-value state for every schema/key listed in
  --template-file. Keys with a user value are written with their current
  effective gsettings value; tracked keys without a user value are written as
  `__RESET__`.
  The base_path argument ({0}) is ignored.

apply mode (action):
  Reads the repo INI file (base_path, {0}) and applies each key via
  `gsettings set`, or `gsettings reset` when the value is `__RESET__`.
"""

from __future__ import annotations

import argparse
import configparser
import shutil
import subprocess
import sys
from functools import lru_cache
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


def gsettings_reset(schema: str, key: str) -> None:
    subprocess.run(
        ["gsettings", "reset", schema, key],
        check=True,
    )


def read_ini(path: Path) -> configparser.RawConfigParser:
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    if path.exists():
        parser.read(path, encoding="utf-8")
    return parser


def write_ini(
    parser: configparser.RawConfigParser,
    path: Path | None,
    *,
    stdout: bool = False,
) -> None:
    if stdout:
        parser.write(sys.stdout)
        return
    if path is None:
        raise ValueError("path is required when stdout is false")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


_FULL_SCHEMA_SUFFIX = ".*"
RESET_MARKER = "__RESET__"


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


@lru_cache(maxsize=None)
def load_gio():
    try:
        import gi
    except ImportError as exc:
        raise RuntimeError("PyGObject is required for gsettings sync") from exc

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
    return Gio


@lru_cache(maxsize=None)
def gio_settings_for_schema(schema: str):
    Gio = load_gio()

    schema_source = Gio.SettingsSchemaSource.get_default()
    if schema_source is None:
        raise RuntimeError("default GSettings schema source is unavailable")

    schema_definition = schema_source.lookup(schema, False)
    if schema_definition is None:
        raise RuntimeError(f"gsettings schema not found: {schema}")

    if schema_definition.get_path() is None:
        raise RuntimeError(
            f"gsettings schema {schema} is relocatable; explicit path support is required"
        )

    return Gio.Settings.new(schema)


def gsettings_has_user_value(schema: str, key: str) -> bool:
    return gio_settings_for_schema(schema).get_user_value(key) is not None


def iter_template_keys(template: configparser.RawConfigParser, section_name: str) -> list[str]:
    if section_name.endswith(_FULL_SCHEMA_SUFFIX):
        return gsettings_list_keys(resolve_schema_name(section_name))
    return list(template.options(section_name))


def run_dump(
    template_path: Path,
    output_path: Path | None,
    *,
    stdout: bool = False,
) -> None:
    """Write current overrides as values and defaults as RESET_MARKER."""
    template = read_ini(template_path)
    output = configparser.RawConfigParser()
    output.optionxform = str

    for section_name in template.sections():
        schema = resolve_schema_name(section_name)
        keys = iter_template_keys(template, section_name)

        output.add_section(section_name)
        for key in keys:
            if not gsettings_has_user_value(schema, key):
                output.set(section_name, key, RESET_MARKER)
                continue
            value = gsettings_get(schema, key)
            if value is None:
                print(
                    f"warning: gsettings get {schema} {key} failed; skipping",
                    file=sys.stderr,
                )
                continue
            output.set(section_name, key, value)

    write_ini(output, output_path, stdout=stdout)


def run_apply(input_path: Path) -> None:
    """Apply repo INI values to gsettings."""
    parser = read_ini(input_path)

    for section_name in parser.sections():
        schema = resolve_schema_name(section_name)
        for key, value in parser.items(section_name):
            if value == RESET_MARKER:
                gsettings_reset(schema, key)
                continue
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
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write dump output to stdout instead of a file.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if shutil.which("gsettings") is None:
        print("gsettings not found; skipping gsettings sync", file=sys.stderr)
        return 0

    if args.mode == "dump":
        if args.output_path is None and not args.stdout:
            print("error: output_path is required for dump mode unless --stdout is used", file=sys.stderr)
            return 2
        template_path = args.template_file if args.template_file is not None else args.base_path
        if not template_path.exists():
            print(
                f"template file not found: {template_path}; skipping gsettings dump",
                file=sys.stderr,
            )
            return 0
        run_dump(template_path, args.output_path, stdout=args.stdout)
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

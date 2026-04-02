#!/usr/bin/env python3
"""
sync_gsettings_gtk.py - Dotdrop trans_update for gtk settings.ini files.

Reads the system settings.ini (base_path, {0}), patches the shared keys with
current org.gnome.desktop.interface gsettings values, and writes the result to
output_path ({1}).

Usage:
  sync_gsettings_gtk.py <base_path> <output_path> --mode gtk3|gtk4
"""

from __future__ import annotations

import argparse
import configparser
import shutil
import subprocess
import sys
from pathlib import Path


# Maps org.gnome.desktop.interface key → gtk settings.ini key.
# Applied to both gtk3 and gtk4 settings.ini files.
_GSETTINGS_TO_GTK_KEY: dict[str, str] = {
    "cursor-size": "gtk-cursor-theme-size",
    "cursor-theme": "gtk-cursor-theme-name",
    "font-name": "gtk-font-name",
    "gtk-theme": "gtk-theme-name",
    "icon-theme": "gtk-icon-theme-name",
}

# gtk3-only: color-scheme → gtk-application-prefer-dark-theme
_GTK3_COLOR_SCHEME_KEY = "gtk-application-prefer-dark-theme"

SCHEMA = "org.gnome.desktop.interface"


def gsettings_get(key: str) -> str | None:
    result = subprocess.run(
        ["gsettings", "get", SCHEMA, key],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def gvariant_to_gtk_value(gvariant: str) -> str:
    """Strip GVariant type annotations to produce a plain gtk settings value."""
    s = gvariant.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    if s.startswith("uint32 "):
        return s[7:].strip()
    if s.startswith("int32 "):
        return s[6:].strip()
    return s


def patch_and_write(base_path: Path, output_path: Path, *, gtk3_extras: bool) -> None:
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(base_path, encoding="utf-8")

    if not parser.has_section("Settings"):
        print(f"warning: no [Settings] section in {base_path}; copying verbatim", file=sys.stderr)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base_path.read_bytes())
        return

    for gsettings_key, gtk_key in _GSETTINGS_TO_GTK_KEY.items():
        value = gsettings_get(gsettings_key)
        if value is None:
            print(f"warning: gsettings get {SCHEMA} {gsettings_key} failed; skipping", file=sys.stderr)
            continue
        parser.set("Settings", gtk_key, gvariant_to_gtk_value(value))

    if gtk3_extras:
        value = gsettings_get("color-scheme")
        if value is not None:
            prefer_dark = "true" if gvariant_to_gtk_value(value) == "prefer-dark" else "false"
            parser.set("Settings", _GTK3_COLOR_SCHEME_KEY, prefer_dark)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        parser.write(f, space_around_delimiters=False)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Dotdrop trans_update: patch gtk settings.ini with gsettings values."
    )
    p.add_argument("base_path", type=Path, help="System settings.ini ({0}).")
    p.add_argument("output_path", type=Path, help="Repo output settings.ini ({1}).")
    p.add_argument("--mode", choices=["gtk3", "gtk4"], required=True)
    args = p.parse_args()

    if shutil.which("gsettings") is None:
        print("gsettings not found; copying settings.ini verbatim", file=sys.stderr)
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_bytes(args.base_path.read_bytes())
        return 0

    if not args.base_path.exists():
        print(f"settings.ini not found: {args.base_path}; skipping", file=sys.stderr)
        return 0

    patch_and_write(args.base_path, args.output_path, gtk3_extras=(args.mode == "gtk3"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

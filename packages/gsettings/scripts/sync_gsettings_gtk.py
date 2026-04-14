#!/usr/bin/env python3
"""
sync_gsettings_gtk.py - Dotdrop trans_update for gtk settings.ini files.

Reads the tracked repo settings.ini via --template-file when available,
patches the managed keys with current gsettings values, and writes the result
to output_path ({1}). The live settings.ini ({0}) is only used as a bootstrap
fallback when no template file is provided.

Usage:
  sync_gsettings_gtk.py <base_path> <output_path> --mode gtk3|gtk4
"""

from __future__ import annotations

import argparse
import configparser
import io
import math
import shutil
import subprocess
import sys
from pathlib import Path

from packages.gsettings.scripts.configparser_utils import CaseSensitiveRawConfigParser


# Maps org.gnome.desktop.interface key → gtk settings.ini key.
# Applied to both gtk3 and gtk4 settings.ini files.
_GSETTINGS_TO_GTK_KEY: dict[str, str] = {
    "cursor-blink": "gtk-cursor-blink",
    "cursor-blink-time": "gtk-cursor-blink-time",
    "cursor-size": "gtk-cursor-theme-size",
    "cursor-theme": "gtk-cursor-theme-name",
    "enable-animations": "gtk-enable-animations",
    "font-name": "gtk-font-name",
    "gtk-theme": "gtk-theme-name",
    "icon-theme": "gtk-icon-theme-name",
}

# gtk3-only: color-scheme → gtk-application-prefer-dark-theme
_GTK3_COLOR_SCHEME_KEY = "gtk-application-prefer-dark-theme"
_GTK_XFT_DPI_KEY = "gtk-xft-dpi"
_TEXT_SCALING_FACTOR_KEY = "text-scaling-factor"
_GTK_DECORATION_LAYOUT_KEY = "gtk-decoration-layout"
_GTK_ENABLE_EVENT_SOUNDS_KEY = "gtk-enable-event-sounds"
_GTK_ENABLE_INPUT_FEEDBACK_SOUNDS_KEY = "gtk-enable-input-feedback-sounds"
_GTK_SOUND_THEME_NAME_KEY = "gtk-sound-theme-name"
_GTK_XFT_ANTIALIAS_KEY = "gtk-xft-antialias"
_GTK_XFT_HINTING_KEY = "gtk-xft-hinting"
_GTK_XFT_HINTSTYLE_KEY = "gtk-xft-hintstyle"
_GTK_XFT_RGBA_KEY = "gtk-xft-rgba"
_DEFAULT_BASE_DPI = 96
_GTK_DPI_SCALE = 1024
_GTK_DEFAULT_XFT_DPI = "-1"

_INTERFACE_SCHEMA = "org.gnome.desktop.interface"
_SOUND_SCHEMA = "org.gnome.desktop.sound"
_WM_PREFERENCES_SCHEMA = "org.gnome.desktop.wm.preferences"


def gsettings_get(key: str, *, schema: str = _INTERFACE_SCHEMA) -> str | None:
    result = subprocess.run(
        ["gsettings", "get", schema, key],
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


def text_scaling_factor_to_gtk_xft_dpi(gvariant: str) -> str:
    scaling_factor = float(gvariant_to_gtk_value(gvariant))
    gtk_xft_dpi = math.ceil(_DEFAULT_BASE_DPI * scaling_factor * _GTK_DPI_SCALE)
    return str(gtk_xft_dpi)


def is_default_text_scaling_factor(gvariant: str) -> bool:
    return math.isclose(float(gvariant_to_gtk_value(gvariant)), 1.0)


def gvariant_bool_to_gtk_numeric(gvariant: str) -> str:
    return "1" if gvariant_to_gtk_value(gvariant) == "true" else "0"


def font_antialiasing_to_gtk_xft_antialias(gvariant: str) -> str:
    return "0" if gvariant_to_gtk_value(gvariant) == "none" else "1"


def font_antialiasing_and_rgba_order_to_gtk_xft_rgba(
    antialiasing_gvariant: str, rgba_order_gvariant: str
) -> str:
    antialiasing = gvariant_to_gtk_value(antialiasing_gvariant)
    if antialiasing != "rgba":
        return "none"
    return gvariant_to_gtk_value(rgba_order_gvariant)


def font_hinting_to_gtk_xft_hinting(gvariant: str) -> str:
    return "0" if gvariant_to_gtk_value(gvariant) == "none" else "1"


def font_hinting_to_gtk_xft_hintstyle(gvariant: str) -> str:
    hinting = gvariant_to_gtk_value(gvariant)
    return {
        "none": "hintnone",
        "slight": "hintslight",
        "medium": "hintmedium",
        "full": "hintfull",
    }[hinting]


def read_settings_ini(path: Path) -> configparser.RawConfigParser:
    parser = CaseSensitiveRawConfigParser()
    parser.read(path, encoding="utf-8")
    return parser


def set_managed_value(
    parser: configparser.RawConfigParser,
    gtk_key: str,
    value: str,
) -> None:
    if parser.has_option("Settings", gtk_key):
        parser.set("Settings", gtk_key, value)


def patch_and_write(
    base_path: Path,
    output_path: Path | None,
    *,
    gtk3_extras: bool,
    template_path: Path | None = None,
    stdout: bool = False,
) -> None:
    effective_template_path = template_path if template_path is not None else base_path
    if not effective_template_path.exists():
        print(
            f"warning: template file not found: {effective_template_path}; using {base_path}",
            file=sys.stderr,
        )
        effective_template_path = base_path
    parser = read_settings_ini(effective_template_path)

    if not parser.has_section("Settings"):
        print(
            f"warning: no [Settings] section in {effective_template_path}; copying verbatim",
            file=sys.stderr,
        )
        if stdout:
            sys.stdout.write(effective_template_path.read_text(encoding="utf-8"))
            return
        if output_path is None:
            raise ValueError("output_path is required when stdout is false")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(effective_template_path.read_bytes())
        return

    for gsettings_key, gtk_key in _GSETTINGS_TO_GTK_KEY.items():
        value = gsettings_get(gsettings_key)
        if value is None:
            print(
                f"warning: gsettings get {_INTERFACE_SCHEMA} {gsettings_key} failed; skipping",
                file=sys.stderr,
            )
            continue
        set_managed_value(parser, gtk_key, gvariant_to_gtk_value(value))

    text_scaling_factor = gsettings_get(_TEXT_SCALING_FACTOR_KEY)
    if text_scaling_factor is None:
        print(
            f"warning: gsettings get {_INTERFACE_SCHEMA} {_TEXT_SCALING_FACTOR_KEY} failed; skipping",
            file=sys.stderr,
        )
    else:
        if is_default_text_scaling_factor(text_scaling_factor):
            # Keep the key at GTK's documented default so future non-default
            # text scaling can still be captured back into the repo template.
            set_managed_value(parser, _GTK_XFT_DPI_KEY, _GTK_DEFAULT_XFT_DPI)
        else:
            set_managed_value(
                parser,
                _GTK_XFT_DPI_KEY,
                text_scaling_factor_to_gtk_xft_dpi(text_scaling_factor),
            )

    decoration_layout = gsettings_get("button-layout", schema=_WM_PREFERENCES_SCHEMA)
    if decoration_layout is None:
        print(
            f"warning: gsettings get {_WM_PREFERENCES_SCHEMA} button-layout failed; skipping",
            file=sys.stderr,
        )
    else:
        set_managed_value(
            parser,
            _GTK_DECORATION_LAYOUT_KEY,
            gvariant_to_gtk_value(decoration_layout),
        )

    sound_theme_name = gsettings_get("theme-name", schema=_SOUND_SCHEMA)
    if sound_theme_name is None:
        print(
            f"warning: gsettings get {_SOUND_SCHEMA} theme-name failed; skipping",
            file=sys.stderr,
        )
    else:
        set_managed_value(
            parser,
            _GTK_SOUND_THEME_NAME_KEY,
            gvariant_to_gtk_value(sound_theme_name),
        )

    event_sounds = gsettings_get("event-sounds", schema=_SOUND_SCHEMA)
    if event_sounds is None:
        print(
            f"warning: gsettings get {_SOUND_SCHEMA} event-sounds failed; skipping",
            file=sys.stderr,
        )
    else:
        set_managed_value(
            parser,
            _GTK_ENABLE_EVENT_SOUNDS_KEY,
            gvariant_bool_to_gtk_numeric(event_sounds),
        )

    input_feedback_sounds = gsettings_get("input-feedback-sounds", schema=_SOUND_SCHEMA)
    if input_feedback_sounds is None:
        print(
            f"warning: gsettings get {_SOUND_SCHEMA} input-feedback-sounds failed; skipping",
            file=sys.stderr,
        )
    else:
        set_managed_value(
            parser,
            _GTK_ENABLE_INPUT_FEEDBACK_SOUNDS_KEY,
            gvariant_bool_to_gtk_numeric(input_feedback_sounds),
        )

    font_antialiasing = gsettings_get("font-antialiasing")
    if font_antialiasing is None:
        print(
            f"warning: gsettings get {_INTERFACE_SCHEMA} font-antialiasing failed; skipping",
            file=sys.stderr,
        )
    else:
        set_managed_value(
            parser,
            _GTK_XFT_ANTIALIAS_KEY,
            font_antialiasing_to_gtk_xft_antialias(font_antialiasing),
        )

    font_hinting = gsettings_get("font-hinting")
    if font_hinting is None:
        print(
            f"warning: gsettings get {_INTERFACE_SCHEMA} font-hinting failed; skipping",
            file=sys.stderr,
        )
    else:
        set_managed_value(
            parser,
            _GTK_XFT_HINTING_KEY,
            font_hinting_to_gtk_xft_hinting(font_hinting),
        )
        set_managed_value(
            parser,
            _GTK_XFT_HINTSTYLE_KEY,
            font_hinting_to_gtk_xft_hintstyle(font_hinting),
        )

    font_rgba_order = gsettings_get("font-rgba-order")
    if font_antialiasing is None or font_rgba_order is None:
        print(
            f"warning: gsettings get {_INTERFACE_SCHEMA} font-rgba-order failed; skipping",
            file=sys.stderr,
        )
    else:
        set_managed_value(
            parser,
            _GTK_XFT_RGBA_KEY,
            font_antialiasing_and_rgba_order_to_gtk_xft_rgba(
                font_antialiasing, font_rgba_order
            ),
        )

    if gtk3_extras:
        value = gsettings_get("color-scheme")
        if value is not None:
            prefer_dark = "1" if gvariant_to_gtk_value(value) == "prefer-dark" else "0"
            set_managed_value(parser, _GTK3_COLOR_SCHEME_KEY, prefer_dark)

    if stdout:
        buffer = io.StringIO()
        parser.write(buffer, space_around_delimiters=False)
        sys.stdout.write(buffer.getvalue())
        return

    if output_path is None:
        raise ValueError("output_path is required when stdout is false")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        parser.write(f, space_around_delimiters=False)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Dotdrop trans_update: patch gtk settings.ini with gsettings values."
    )
    p.add_argument("base_path", type=Path, help="System settings.ini ({0}).")
    p.add_argument("output_path", type=Path, nargs="?", default=None, help="Repo output settings.ini ({1}).")
    p.add_argument("--mode", choices=["gtk3", "gtk4"], required=True)
    p.add_argument(
        "--template-file",
        type=Path,
        default=None,
        help="Tracked repo settings.ini template. Defaults to base_path when not provided.",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Write patched settings.ini to stdout instead of a file.",
    )
    args = p.parse_args()

    if shutil.which("gsettings") is None:
        print("gsettings not found; copying settings.ini verbatim", file=sys.stderr)
        if args.stdout:
            sys.stdout.write(args.base_path.read_text(encoding="utf-8"))
            return 0
        if args.output_path is None:
            print("output_path is required unless --stdout is used", file=sys.stderr)
            return 2
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_bytes(args.base_path.read_bytes())
        return 0

    if not args.base_path.exists():
        print(f"settings.ini not found: {args.base_path}; skipping", file=sys.stderr)
        return 0

    patch_and_write(
        args.base_path,
        args.output_path,
        gtk3_extras=(args.mode == "gtk3"),
        template_path=args.template_file,
        stdout=args.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

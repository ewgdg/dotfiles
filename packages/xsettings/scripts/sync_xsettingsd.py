#!/usr/bin/env python3
"""
sync_xsettingsd.py - Dotman trans_update for xsettingsd.conf.

Reads desktop settings from XDG desktop settings portal when available, patches
tracked repo template with managed XSETTINGS keys, and writes result to
output_path ({1}). When portal is unavailable or missing individual values,
the live xsettingsd.conf ({0}) is used as fallback source.

Usage:
  sync_xsettingsd.py <base_path> <output_path>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# Portal API is generic (`org.freedesktop.portal.Settings`), but namespaces are
# backend-defined. Current Linux setup exposes GNOME namespaces here, while the
# generic `org.freedesktop.appearance` namespace is too narrow for full XSETTINGS.
_APPEARANCE_NAMESPACE = "org.freedesktop.appearance"
_INTERFACE_SCHEMA = "org.gnome.desktop.interface"
_SOUND_SCHEMA = "org.gnome.desktop.sound"
_WM_PREFERENCES_SCHEMA = "org.gnome.desktop.wm.preferences"
_KNOWN_BACKEND_NAMESPACES = frozenset(
    {
        _INTERFACE_SCHEMA,
        _SOUND_SCHEMA,
        _WM_PREFERENCES_SCHEMA,
    }
)

_MANAGED_XSETTINGS_KEYS = frozenset(
    {
        "Gtk/EnableAnimations",
        "Net/CursorBlink",
        "Net/CursorBlinkTime",
        "Net/ThemeName",
        "Net/IconThemeName",
        "Gtk/CursorThemeName",
        "Gtk/CursorThemeSize",
        "Gtk/FontName",
        "Gtk/DecorationLayout",
        "Gtk/EnablePrimaryPaste",
        "Net/SoundThemeName",
        "Net/EnableEventSounds",
        "Net/EnableInputFeedbackSounds",
        # Existing live config currently uses legacy alias without Net/ prefix.
        "EnableInputFeedbackSounds",
        "Xft/Antialias",
        "Xft/HintStyle",
        "Xft/Hinting",
        "Xft/RGBA",
    }
)

_LINE_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<key>\S+)(?P<spacing>\s+)(?P<value>.*?)(?P<newline>\r?\n?)$"
)


def format_xsettings_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def format_xsettings_bool(value: bool) -> str:
    return "1" if value else "0"


def font_antialiasing_to_xft_antialias(value: str) -> str:
    return "0" if value == "none" else "1"


def font_hinting_to_xft_hinting(value: str) -> str:
    return "0" if value == "none" else "1"


def font_hinting_to_xft_hintstyle(value: str) -> str:
    return format_xsettings_string(
        {
            "none": "hintnone",
            "slight": "hintslight",
            "medium": "hintmedium",
            "full": "hintfull",
        }[value]
    )


def font_antialiasing_and_rgba_order_to_xft_rgba(
    antialiasing: str, rgba_order: str
) -> str:
    if antialiasing != "rgba":
        return format_xsettings_string("none")
    return format_xsettings_string(rgba_order)


def read_portal_settings() -> dict[str, dict[str, Any]] | None:
    try:
        from gi.repository import Gio, GLib
    except ImportError:
        return None

    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            None,
        )
        result = proxy.call_sync(
            "ReadAll",
            GLib.Variant("(as)", ([],)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except Exception:
        return None

    unpacked = result.unpack()
    if not unpacked:
        return None
    namespaces = unpacked[0]
    if not isinstance(namespaces, dict):
        return None
    return namespaces


def portal_warnings(portal_settings: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    available_namespaces = sorted(portal_settings)
    known_backend_namespaces = sorted(
        namespace
        for namespace in available_namespaces
        if namespace in _KNOWN_BACKEND_NAMESPACES
    )

    if _APPEARANCE_NAMESPACE not in portal_settings:
        warnings.append(
            "portal missing org.freedesktop.appearance namespace; portable appearance hints unavailable"
        )

    if not known_backend_namespaces:
        warnings.append(
            "portal exposes no known backend-specific namespaces for xsettings capture; "
            f"available namespaces: {', '.join(available_namespaces) if available_namespaces else '(none)'}"
        )
        return warnings

    missing_backend_namespaces = sorted(
        _KNOWN_BACKEND_NAMESPACES - set(known_backend_namespaces)
    )
    if missing_backend_namespaces:
        warnings.append(
            "portal missing known backend namespaces; live xsettingsd.conf will fill gaps: "
            + ", ".join(missing_backend_namespaces)
        )

    return warnings


def portal_values_to_xsettings(
    portal_settings: dict[str, dict[str, Any]],
) -> dict[str, str]:
    result: dict[str, str] = {}

    appearance_settings = portal_settings.get(_APPEARANCE_NAMESPACE, {})
    interface_settings = portal_settings.get(_INTERFACE_SCHEMA, {})
    sound_settings = portal_settings.get(_SOUND_SCHEMA, {})
    wm_settings = portal_settings.get(_WM_PREFERENCES_SCHEMA, {})

    # Keep generic appearance namespace in read path first. Today it does not expose
    # enough detail to derive exact XSETTINGS theme/font/icon values safely.
    if not isinstance(appearance_settings, dict):
        appearance_settings = {}

    string_mappings = {
        "Net/ThemeName": interface_settings.get("gtk-theme"),
        "Net/IconThemeName": interface_settings.get("icon-theme"),
        "Gtk/CursorThemeName": interface_settings.get("cursor-theme"),
        "Gtk/FontName": interface_settings.get("font-name"),
        "Gtk/DecorationLayout": wm_settings.get("button-layout"),
        "Net/SoundThemeName": sound_settings.get("theme-name"),
    }
    for xsettings_key, value in string_mappings.items():
        if isinstance(value, str):
            result[xsettings_key] = format_xsettings_string(value)

    enable_animations = interface_settings.get("enable-animations")
    if isinstance(enable_animations, bool):
        result["Gtk/EnableAnimations"] = format_xsettings_bool(enable_animations)

    cursor_blink = interface_settings.get("cursor-blink")
    if isinstance(cursor_blink, bool):
        result["Net/CursorBlink"] = format_xsettings_bool(cursor_blink)

    cursor_blink_time = interface_settings.get("cursor-blink-time")
    if isinstance(cursor_blink_time, int) and not isinstance(cursor_blink_time, bool):
        result["Net/CursorBlinkTime"] = str(cursor_blink_time)

    cursor_size = interface_settings.get("cursor-size")
    if isinstance(cursor_size, int) and not isinstance(cursor_size, bool):
        result["Gtk/CursorThemeSize"] = str(cursor_size)

    enable_primary_paste = interface_settings.get("gtk-enable-primary-paste")
    if isinstance(enable_primary_paste, bool):
        result["Gtk/EnablePrimaryPaste"] = format_xsettings_bool(enable_primary_paste)

    event_sounds = sound_settings.get("event-sounds")
    if isinstance(event_sounds, bool):
        result["Net/EnableEventSounds"] = format_xsettings_bool(event_sounds)

    input_feedback_sounds = sound_settings.get("input-feedback-sounds")
    if isinstance(input_feedback_sounds, bool):
        rendered_input_feedback_sounds = format_xsettings_bool(input_feedback_sounds)
        result["Net/EnableInputFeedbackSounds"] = rendered_input_feedback_sounds
        result["EnableInputFeedbackSounds"] = rendered_input_feedback_sounds

    font_antialiasing = interface_settings.get("font-antialiasing")
    if isinstance(font_antialiasing, str):
        result["Xft/Antialias"] = font_antialiasing_to_xft_antialias(font_antialiasing)

    font_hinting = interface_settings.get("font-hinting")
    if isinstance(font_hinting, str):
        result["Xft/Hinting"] = font_hinting_to_xft_hinting(font_hinting)
        result["Xft/HintStyle"] = font_hinting_to_xft_hintstyle(font_hinting)

    font_rgba_order = interface_settings.get("font-rgba-order")
    if isinstance(font_antialiasing, str) and isinstance(font_rgba_order, str):
        result["Xft/RGBA"] = font_antialiasing_and_rgba_order_to_xft_rgba(
            font_antialiasing,
            font_rgba_order,
        )

    return result


def read_live_xsettings_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts
        if key in _MANAGED_XSETTINGS_KEYS:
            values[key] = value
    return values


def patch_template(template_text: str, managed_values: dict[str, str]) -> str:
    rendered_lines: list[str] = []
    for line in template_text.splitlines(keepends=True):
        match = _LINE_PATTERN.match(line)
        if match is None:
            rendered_lines.append(line)
            continue

        key = match.group("key")
        if key not in _MANAGED_XSETTINGS_KEYS or key not in managed_values:
            rendered_lines.append(line)
            continue

        rendered_lines.append(
            f"{match.group('indent')}{key}{match.group('spacing')}{managed_values[key]}{match.group('newline')}"
        )

    return "".join(rendered_lines)


def patch_and_write(
    base_path: Path,
    output_path: Path | None,
    *,
    template_path: Path | None = None,
    stdout: bool = False,
) -> None:
    effective_template_path = template_path if template_path is not None else base_path
    if not effective_template_path.exists():
        if base_path.exists():
            print(
                f"warning: template file not found: {effective_template_path}; using {base_path}",
                file=sys.stderr,
            )
            effective_template_path = base_path
        else:
            raise FileNotFoundError(
                f"neither template nor live file exists: {effective_template_path}, {base_path}"
            )

    managed_values: dict[str, str] = {}
    portal_settings = read_portal_settings()
    if portal_settings is None:
        print(
            "warning: XDG desktop settings portal unavailable; falling back to live xsettingsd.conf",
            file=sys.stderr,
        )
    else:
        for warning in portal_warnings(portal_settings):
            print(f"warning: {warning}", file=sys.stderr)
        managed_values.update(portal_values_to_xsettings(portal_settings))
        if not managed_values:
            print(
                "warning: portal returned no xsettings-compatible values; falling back to live xsettingsd.conf",
                file=sys.stderr,
            )

    # DPI keys are intentionally unmanaged here. We want to probe whether
    # xwayland-satellite/wp_viewporter scaling alone is sufficient once xsettingsd owns
    # XSETTINGS, before adding machine-specific DPI rendering from Niri scale.
    # Portal is preferred source, but live config remains fallback for keys the portal
    # does not expose or when the portal backend changes and stops exposing known namespaces.
    for key, value in read_live_xsettings_values(base_path).items():
        managed_values.setdefault(key, value)

    template_text = effective_template_path.read_text(encoding="utf-8")
    rendered = patch_template(template_text, managed_values)

    if stdout:
        sys.stdout.write(rendered)
        return

    if output_path is None:
        raise ValueError("output_path is required when stdout is false")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dotman trans_update: patch xsettingsd.conf with portal settings."
    )
    parser.add_argument("base_path", type=Path, help="Live xsettingsd.conf ({0}).")
    parser.add_argument(
        "output_path",
        type=Path,
        nargs="?",
        default=None,
        help="Repo output xsettingsd.conf ({1}).",
    )
    parser.add_argument(
        "--template-file",
        type=Path,
        default=None,
        help="Tracked repo xsettingsd.conf template. Defaults to base_path when not provided.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write patched xsettingsd.conf to stdout instead of a file.",
    )
    args = parser.parse_args()

    if not args.base_path.exists() and (
        args.template_file is None or not args.template_file.exists()
    ):
        print(
            f"xsettingsd.conf not found: {args.base_path}; skipping",
            file=sys.stderr,
        )
        return 0

    patch_and_write(
        args.base_path,
        args.output_path,
        template_path=args.template_file,
        stdout=args.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import configparser
import shutil
import subprocess
import sys
from pathlib import Path


def read_settings_file(settings_path: Path) -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    with settings_path.open("r", encoding="utf-8") as settings_file:
        parser.read_file(settings_file)
    if "Settings" not in parser:
        raise KeyError(f"missing [Settings] section in {settings_path}")
    return parser["Settings"]


def build_gsettings_updates(
    gtk3_settings: configparser.SectionProxy,
) -> list[tuple[str, str, str]]:
    updates: list[tuple[str, str, str]] = []

    shared_setting_to_key = {
        "gtk-icon-theme-name": "icon-theme",
        "gtk-cursor-theme-name": "cursor-theme",
        "gtk-cursor-theme-size": "cursor-size",
    }

    gtk_theme_name = gtk3_settings.get("gtk-theme-name")
    if gtk_theme_name:
        updates.append(("org.gnome.desktop.interface", "gtk-theme", gtk_theme_name))

    for gtk_setting_name, gsettings_key in shared_setting_to_key.items():
        setting_value = gtk3_settings.get(gtk_setting_name)
        if setting_value:
            updates.append(
                ("org.gnome.desktop.interface", gsettings_key, setting_value)
            )

    prefer_dark_theme = gtk3_settings.get("gtk-application-prefer-dark-theme")
    if prefer_dark_theme is not None:
        color_scheme = "prefer-dark" if prefer_dark_theme.lower() == "true" else "default"
        updates.append(
            ("org.gnome.desktop.interface", "color-scheme", color_scheme)
        )

    return updates


def run_gsettings_set(schema_name: str, key_name: str, key_value: str) -> None:
    subprocess.run(
        ["gsettings", "set", schema_name, key_name, key_value],
        check=True,
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: sync_gtk_gsettings.py <gtk-3.0-settings.ini>",
            file=sys.stderr,
        )
        return 2

    if shutil.which("gsettings") is None:
        print("gsettings not found; skipping GTK GSettings sync", file=sys.stderr)
        return 0

    gtk3_settings_path = Path(sys.argv[1]).expanduser()
    gtk3_settings = read_settings_file(gtk3_settings_path)
    updates = build_gsettings_updates(gtk3_settings)

    for schema_name, key_name, key_value in updates:
        run_gsettings_set(schema_name, key_name, key_value)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import configparser
from pathlib import Path

from scripts.configparser_utils import CaseSensitiveRawConfigParser
from packages.gsettings.scripts import sync_gsettings_gtk as module


def read_settings(path: Path) -> configparser.RawConfigParser:
    parser = CaseSensitiveRawConfigParser()
    parser.read(path, encoding="utf-8")
    return parser


def test_patch_and_write_sets_gtk_xft_dpi_from_text_scaling_factor(
    monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "settings.ini"
    output_path = tmp_path / "output.ini"
    base_path.write_text(
        "[Settings]\n"
        "gtk-primary-button-warps-slider=true\n"
        "gtk-font-name=Adwaita Sans 11\n"
        "gtk-theme-name=Adwaita\n"
        "gtk-xft-dpi=130252\n",
        encoding="utf-8",
    )
    output_path.write_text(
        "[Settings]\n"
        "gtk-cursor-blink=false\n"
        "gtk-cursor-blink-time=1200\n"
        "gtk-cursor-theme-name=Adwaita\n"
        "gtk-cursor-theme-size=16\n"
        "gtk-decoration-layout=appmenu:close\n"
        "gtk-enable-animations=false\n"
        "gtk-font-name=Adwaita Sans 10\n"
        "gtk-icon-theme-name=Adwaita\n"
        "gtk-sound-theme-name=__unset__\n"
        "gtk-theme-name=Adwaita\n"
        "gtk-xft-antialias=0\n"
        "gtk-xft-dpi=130252\n"
        "gtk-xft-hinting=0\n"
        "gtk-xft-hintstyle=hintnone\n"
        "gtk-xft-rgba=rgb\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "gsettings_get",
        lambda key, schema=module._INTERFACE_SCHEMA: {
            (module._INTERFACE_SCHEMA, "cursor-blink"): "true",
            (module._INTERFACE_SCHEMA, "cursor-blink-time"): "1000",
            (module._INTERFACE_SCHEMA, "cursor-size"): "uint32 24",
            (module._INTERFACE_SCHEMA, "cursor-theme"): "'Bibata-Modern-Ice'",
            (module._INTERFACE_SCHEMA, "enable-animations"): "true",
            (module._INTERFACE_SCHEMA, "font-antialiasing"): "'grayscale'",
            (module._INTERFACE_SCHEMA, "font-hinting"): "'slight'",
            (module._INTERFACE_SCHEMA, "font-name"): "'Adwaita Sans 11'",
            (module._INTERFACE_SCHEMA, "font-rgba-order"): "'rgb'",
            (module._INTERFACE_SCHEMA, "gtk-theme"): "'Adwaita'",
            (module._INTERFACE_SCHEMA, "icon-theme"): "'Papirus-Dark'",
            (module._INTERFACE_SCHEMA, "text-scaling-factor"): "1.0",
            (module._SOUND_SCHEMA, "event-sounds"): "true",
            (module._SOUND_SCHEMA, "input-feedback-sounds"): "false",
            (module._SOUND_SCHEMA, "theme-name"): "'freedesktop'",
            (module._WM_PREFERENCES_SCHEMA, "button-layout"): "'icon:minimize,maximize,close'",
        }.get((schema, key)),
    )

    module.patch_and_write(
        base_path,
        output_path,
        gtk3_extras=False,
        template_path=output_path,
    )

    result = read_settings(output_path)

    assert result.get("Settings", "gtk-cursor-blink") == "true"
    assert result.get("Settings", "gtk-cursor-blink-time") == "1000"
    assert result.get("Settings", "gtk-decoration-layout") == "icon:minimize,maximize,close"
    assert result.get("Settings", "gtk-enable-animations") == "true"
    assert result.get("Settings", "gtk-sound-theme-name") == "freedesktop"
    assert result.get("Settings", "gtk-xft-antialias") == "1"
    assert result.get("Settings", "gtk-xft-hinting") == "1"
    assert result.get("Settings", "gtk-xft-hintstyle") == "hintslight"
    assert result.get("Settings", "gtk-xft-rgba") == "none"
    assert result.get("Settings", "gtk-xft-dpi") == "98304"
    assert not result.has_option("Settings", "gtk-enable-event-sounds")
    assert not result.has_option("Settings", "gtk-enable-input-feedback-sounds")
    assert not result.has_option("Settings", "gtk-primary-button-warps-slider")


def test_patch_and_write_leaves_existing_gtk_xft_dpi_when_scaling_is_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "settings.ini"
    output_path = tmp_path / "output.ini"
    base_path.write_text(
        "[Settings]\n"
        "gtk-xft-dpi=130252\n",
        encoding="utf-8",
    )
    output_path.write_text(
        "[Settings]\n"
        "gtk-xft-dpi=130252\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "gsettings_get", lambda key, schema=module._INTERFACE_SCHEMA: None)

    module.patch_and_write(
        base_path,
        output_path,
        gtk3_extras=False,
        template_path=output_path,
    )

    result = read_settings(output_path)

    assert result.get("Settings", "gtk-xft-dpi") == "130252"


def test_patch_and_write_uses_repo_template_to_drop_live_only_keys(
    monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "settings.ini"
    output_path = tmp_path / "output.ini"
    base_path.write_text(
        "[Settings]\n"
        "gtk-modules=colorreload-gtk-module:window-decorations-gtk-module\n"
        "gtk-primary-button-warps-slider=true\n",
        encoding="utf-8",
    )
    output_path.write_text(
        "[Settings]\n"
        "gtk-theme-name=Adwaita\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "gsettings_get",
        lambda key, schema=module._INTERFACE_SCHEMA: {
            (module._INTERFACE_SCHEMA, "gtk-theme"): "'Adwaita-dark'",
        }.get((schema, key)),
    )

    module.patch_and_write(
        base_path,
        output_path,
        gtk3_extras=False,
        template_path=output_path,
    )

    result = read_settings(output_path)

    assert result.get("Settings", "gtk-theme-name") == "Adwaita-dark"
    assert list(result["Settings"]) == ["gtk-theme-name"]


def test_patch_and_write_prefers_explicit_template_file_over_live_output(
    monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "live-settings.ini"
    template_path = tmp_path / "repo-settings.ini"
    output_path = tmp_path / "output.ini"
    base_path.write_text(
        "[Settings]\n"
        "gtk-modules=colorreload-gtk-module:window-decorations-gtk-module\n"
        "gtk-primary-button-warps-slider=true\n",
        encoding="utf-8",
    )
    template_path.write_text(
        "[Settings]\n"
        "gtk-theme-name=Adwaita\n",
        encoding="utf-8",
    )
    output_path.write_text(base_path.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        module,
        "gsettings_get",
        lambda key, schema=module._INTERFACE_SCHEMA: {
            (module._INTERFACE_SCHEMA, "gtk-theme"): "'Adwaita-dark'",
        }.get((schema, key)),
    )

    module.patch_and_write(
        base_path,
        output_path,
        gtk3_extras=False,
        template_path=template_path,
    )

    result = read_settings(output_path)

    assert result.get("Settings", "gtk-theme-name") == "Adwaita-dark"
    assert list(result["Settings"]) == ["gtk-theme-name"]


def test_text_scaling_factor_to_gtk_xft_dpi_uses_96_dpi_baseline() -> None:
    assert module.text_scaling_factor_to_gtk_xft_dpi("1.0") == "98304"
    assert module.text_scaling_factor_to_gtk_xft_dpi("0.85") == "83559"


def test_font_antialiasing_and_rgba_order_to_gtk_xft_rgba_respects_mode() -> None:
    assert (
        module.font_antialiasing_and_rgba_order_to_gtk_xft_rgba("'rgba'", "'rgb'")
        == "rgb"
    )
    assert (
        module.font_antialiasing_and_rgba_order_to_gtk_xft_rgba("'grayscale'", "'rgb'")
        == "none"
    )

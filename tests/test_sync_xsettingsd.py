from __future__ import annotations

import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "packages/xsettings/scripts/sync_xsettingsd.py"
_MODULE_SPEC = importlib.util.spec_from_file_location("xsettings_sync_module", _MODULE_PATH)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise RuntimeError(f"failed to load xsettings sync module from {_MODULE_PATH}")
module = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(module)


_PORTAL_SETTINGS = {
    module._INTERFACE_SCHEMA: {
        "cursor-blink": True,
        "cursor-blink-time": 1200,
        "cursor-size": 24,
        "cursor-theme": "Bibata-Modern-Ice",
        "enable-animations": True,
        "font-antialiasing": "grayscale",
        "font-hinting": "slight",
        "font-name": "Adwaita Sans 11",
        "font-rgba-order": "rgb",
        "gtk-enable-primary-paste": True,
        "gtk-theme": "Adwaita",
        "icon-theme": "Papirus-Dark",
    },
    module._SOUND_SCHEMA: {
        "event-sounds": True,
        "input-feedback-sounds": False,
        "theme-name": "freedesktop",
    },
    module._WM_PREFERENCES_SCHEMA: {
        "button-layout": "icon:minimize,maximize,close",
    },
}

_APPEARANCE_ONLY_PORTAL_SETTINGS = {
    module._APPEARANCE_NAMESPACE: {
        "color-scheme": 1,
        "contrast": 0,
    },
    "org.kde.foo": {
        "theme": "Breeze",
    },
}


def test_patch_and_write_prefers_portal_values_and_preserves_comments(
    monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "live.conf"
    template_path = tmp_path / "repo.conf"
    output_path = tmp_path / "output.conf"

    base_path.write_text(
        "Gtk/Modules \"live-only\"\n"
        "Net/ThemeName \"Old\"\n",
        encoding="utf-8",
    )
    template_path.write_text(
        "# managed by dotman\n"
        "Gtk/EnableAnimations 0\n"
        "Net/CursorBlinkTime 1000\n"
        "Net/CursorBlink 0\n"
        "Net/ThemeName \"Old\"\n"
        "Net/IconThemeName \"Old\"\n"
        "\n"
        "Gtk/CursorThemeName \"Old\"\n"
        "Gtk/CursorThemeSize 16\n"
        "Gtk/FontName \"Old Font 10\"\n"
        "Gtk/DecorationLayout \"menu:close\"\n"
        "Gtk/EnablePrimaryPaste 0\n"
        "\n"
        "Net/SoundThemeName \"old\"\n"
        "Net/EnableEventSounds 0\n"
        "EnableInputFeedbackSounds 1\n"
        "\n"
        "Xft/Antialias 0\n"
        "Xft/HintStyle \"hintnone\"\n"
        "Xft/Hinting 0\n"
        "Xft/RGBA \"rgb\"\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "read_portal_settings", lambda: _PORTAL_SETTINGS)

    module.patch_and_write(
        base_path,
        output_path,
        template_path=template_path,
    )

    result = output_path.read_text(encoding="utf-8")

    assert "# managed by dotman\n" in result
    assert "Gtk/EnableAnimations 1\n" in result
    assert "Net/CursorBlinkTime 1200\n" in result
    assert "Net/CursorBlink 1\n" in result
    assert 'Net/ThemeName "Adwaita"\n' in result
    assert 'Net/IconThemeName "Papirus-Dark"\n' in result
    assert 'Gtk/CursorThemeName "Bibata-Modern-Ice"\n' in result
    assert "Gtk/CursorThemeSize 24\n" in result
    assert 'Gtk/FontName "Adwaita Sans 11"\n' in result
    assert 'Gtk/DecorationLayout "icon:minimize,maximize,close"\n' in result
    assert "Gtk/EnablePrimaryPaste 1\n" in result
    assert 'Net/SoundThemeName "freedesktop"\n' in result
    assert "Net/EnableEventSounds 1\n" in result
    assert "EnableInputFeedbackSounds 0\n" in result
    assert "Xft/Antialias 1\n" in result
    assert 'Xft/HintStyle "hintslight"\n' in result
    assert "Xft/Hinting 1\n" in result
    assert 'Xft/RGBA "none"\n' in result
    assert "Gtk/Modules" not in result


def test_patch_and_write_falls_back_to_live_file_when_portal_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "live.conf"
    template_path = tmp_path / "repo.conf"
    output_path = tmp_path / "output.conf"

    base_path.write_text(
        'Net/ThemeName "Live Theme"\n'
        'Gtk/CursorThemeName "Live Cursor"\n',
        encoding="utf-8",
    )
    template_path.write_text(
        'Net/ThemeName "Repo Theme"\n'
        'Gtk/CursorThemeName "Repo Cursor"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "read_portal_settings", lambda: None)

    module.patch_and_write(
        base_path,
        output_path,
        template_path=template_path,
    )

    assert output_path.read_text(encoding="utf-8") == (
        'Net/ThemeName "Live Theme"\n'
        'Gtk/CursorThemeName "Live Cursor"\n'
    )


def test_patch_and_write_uses_repo_template_to_drop_live_only_keys(
    monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "live.conf"
    template_path = tmp_path / "repo.conf"
    output_path = tmp_path / "output.conf"

    base_path.write_text(
        'Gtk/Modules "colorreload-gtk-module"\n'
        'Net/ThemeName "Live Theme"\n',
        encoding="utf-8",
    )
    template_path.write_text(
        'Net/ThemeName "Repo Theme"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "read_portal_settings", lambda: None)

    module.patch_and_write(
        base_path,
        output_path,
        template_path=template_path,
    )

    assert output_path.read_text(encoding="utf-8") == 'Net/ThemeName "Live Theme"\n'


def test_portal_values_to_xsettings_maps_known_keys() -> None:
    result = module.portal_values_to_xsettings(_PORTAL_SETTINGS)

    assert result == {
        'Gtk/EnableAnimations': '1',
        'Net/CursorBlink': '1',
        'Net/CursorBlinkTime': '1200',
        'Net/ThemeName': '"Adwaita"',
        'Net/IconThemeName': '"Papirus-Dark"',
        'Gtk/CursorThemeName': '"Bibata-Modern-Ice"',
        'Gtk/CursorThemeSize': '24',
        'Gtk/FontName': '"Adwaita Sans 11"',
        'Gtk/DecorationLayout': '"icon:minimize,maximize,close"',
        'Gtk/EnablePrimaryPaste': '1',
        'Net/SoundThemeName': '"freedesktop"',
        'Net/EnableEventSounds': '1',
        'Net/EnableInputFeedbackSounds': '0',
        'EnableInputFeedbackSounds': '0',
        'Xft/Antialias': '1',
        'Xft/HintStyle': '"hintslight"',
        'Xft/Hinting': '1',
        'Xft/RGBA': '"none"',
    }


def test_patch_and_write_warns_when_portal_has_no_known_backend_namespaces(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    base_path = tmp_path / "live.conf"
    template_path = tmp_path / "repo.conf"
    output_path = tmp_path / "output.conf"

    base_path.write_text(
        'Net/ThemeName "Live Theme"\n'
        'Net/IconThemeName "Live Icons"\n',
        encoding="utf-8",
    )
    template_path.write_text(
        'Net/ThemeName "Repo Theme"\n'
        'Net/IconThemeName "Repo Icons"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "read_portal_settings",
        lambda: _APPEARANCE_ONLY_PORTAL_SETTINGS,
    )

    module.patch_and_write(
        base_path,
        output_path,
        template_path=template_path,
    )

    stderr = capsys.readouterr().err

    assert "no known backend-specific namespaces" in stderr
    assert module._APPEARANCE_NAMESPACE in stderr
    assert 'Net/ThemeName "Live Theme"\n' in output_path.read_text(encoding="utf-8")
    assert 'Net/IconThemeName "Live Icons"\n' in output_path.read_text(encoding="utf-8")


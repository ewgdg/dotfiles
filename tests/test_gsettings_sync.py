from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import gsettings_sync as module


def test_run_dump_preserves_full_schema_section_names(
    monkeypatch, tmp_path: Path
) -> None:
    template_path = tmp_path / "nautilus.ini"
    template_path.write_text(
        "[org.gnome.nautilus.icon-view.*]\n\n"
        "[org.gnome.nautilus.preferences]\n"
        "default-folder-viewer = ignored\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "output.ini"

    monkeypatch.setattr(
        module,
        "gsettings_list_keys",
        lambda schema: ["captions", "default-zoom-level"]
        if schema == "org.gnome.nautilus.icon-view"
        else [],
    )
    monkeypatch.setattr(
        module,
        "gsettings_get",
        lambda schema, key: {
            ("org.gnome.nautilus.icon-view", "captions"): "['none', 'none', 'none']",
            ("org.gnome.nautilus.icon-view", "default-zoom-level"): "'medium'",
            ("org.gnome.nautilus.preferences", "default-folder-viewer"): "'icon-view'",
        }.get((schema, key)),
    )
    monkeypatch.setattr(
        module,
        "gsettings_has_user_value",
        lambda schema, key: (schema, key)
        in {
            ("org.gnome.nautilus.icon-view", "captions"),
            ("org.gnome.nautilus.icon-view", "default-zoom-level"),
            ("org.gnome.nautilus.preferences", "default-folder-viewer"),
        },
    )

    module.run_dump(template_path, output_path)

    result = module.read_ini(output_path)

    assert result.sections() == [
        "org.gnome.nautilus.icon-view.*",
        "org.gnome.nautilus.preferences",
    ]
    assert result.get(
        "org.gnome.nautilus.icon-view.*",
        "default-zoom-level",
    ) == "'medium'"
    assert (
        result.get("org.gnome.nautilus.preferences", "default-folder-viewer")
        == "'icon-view'"
    )


def test_run_dump_preserves_explicit_template_key_order(
    monkeypatch, tmp_path: Path
) -> None:
    template_path = tmp_path / "desktop.ini"
    template_path.write_text(
        "[org.gnome.desktop.interface]\n"
        "icon-theme = ignored\n"
        "gtk-theme = ignored\n"
        "cursor-theme = ignored\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "output.ini"

    monkeypatch.setattr(
        module,
        "gsettings_get",
        lambda schema, key: {
            ("org.gnome.desktop.interface", "icon-theme"): "'Papirus-Dark'",
            ("org.gnome.desktop.interface", "gtk-theme"): "'Adwaita'",
            ("org.gnome.desktop.interface", "cursor-theme"): "'Bibata-Modern-Ice'",
        }.get((schema, key)),
    )
    monkeypatch.setattr(
        module,
        "gsettings_has_user_value",
        lambda schema, key: True,
    )

    module.run_dump(template_path, output_path)

    result = module.read_ini(output_path)

    assert list(result["org.gnome.desktop.interface"]) == [
        "icon-theme",
        "gtk-theme",
        "cursor-theme",
    ]


def test_run_dump_marks_unoverridden_explicit_keys_with_reset_token(
    monkeypatch, tmp_path: Path
) -> None:
    template_path = tmp_path / "desktop.ini"
    template_path.write_text(
        "[org.gnome.desktop.interface]\n"
        "color-scheme = ignored\n"
        "icon-theme = ignored\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "output.ini"
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "gsettings_get",
        lambda schema, key: calls.append((schema, key)) or "'Papirus-Dark'",
    )
    monkeypatch.setattr(
        module,
        "gsettings_has_user_value",
        lambda schema, key: key == "icon-theme",
    )

    module.run_dump(template_path, output_path)

    result = module.read_ini(output_path)

    assert result.get("org.gnome.desktop.interface", "color-scheme") == "__RESET__"
    assert result.get("org.gnome.desktop.interface", "icon-theme") == "'Papirus-Dark'"
    assert calls == [("org.gnome.desktop.interface", "icon-theme")]


def test_run_dump_marks_unoverridden_wildcard_keys_with_reset_token(
    monkeypatch, tmp_path: Path
) -> None:
    template_path = tmp_path / "nautilus.ini"
    template_path.write_text(
        "[org.gnome.nautilus.preferences.*]\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "output.ini"
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "gsettings_list_keys",
        lambda schema: ["click-policy", "show-hidden-files"],
    )
    monkeypatch.setattr(
        module,
        "gsettings_has_user_value",
        lambda schema, key: key == "click-policy",
    )
    monkeypatch.setattr(
        module,
        "gsettings_get",
        lambda schema, key: calls.append((schema, key)) or "'double'",
    )

    module.run_dump(template_path, output_path)

    result = module.read_ini(output_path)

    assert result.get("org.gnome.nautilus.preferences.*", "click-policy") == "'double'"
    assert result.get("org.gnome.nautilus.preferences.*", "show-hidden-files") == "__RESET__"
    assert calls == [("org.gnome.nautilus.preferences", "click-policy")]


def test_gsettings_has_user_value_uses_gio_user_value(monkeypatch) -> None:
    class FakeSettings:
        def get_user_value(self, key: str):
            return object() if key == "mode" else None

    monkeypatch.setattr(module, "gio_settings_for_schema", lambda schema: FakeSettings())

    assert module.gsettings_has_user_value("org.gnome.system.proxy", "mode") is True
    assert module.gsettings_has_user_value("org.gnome.system.proxy", "host") is False


def test_gio_settings_for_schema_rejects_relocatable_schema(monkeypatch) -> None:
    class FakeSchemaDefinition:
        def get_path(self):
            return None

    class FakeSchemaSource:
        def lookup(self, schema: str, recursive: bool):
            return FakeSchemaDefinition()

    fake_gio = SimpleNamespace(
        SettingsSchemaSource=SimpleNamespace(get_default=lambda: FakeSchemaSource()),
        Settings=SimpleNamespace(new=lambda schema: object()),
    )
    monkeypatch.setattr(module, "load_gio", lambda: fake_gio)
    module.gio_settings_for_schema.cache_clear()

    try:
        try:
            module.gio_settings_for_schema("org.example.relocatable")
        except RuntimeError as exc:
            assert "relocatable" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for relocatable schema")
    finally:
        module.gio_settings_for_schema.cache_clear()


def test_run_apply_strips_full_schema_suffix_before_setting_keys(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "nautilus.ini"
    input_path.write_text(
        "[org.gnome.nautilus.icon-view.*]\n"
        "default-zoom-level = 'medium'\n\n"
        "[org.gnome.nautilus.preferences]\n"
        "default-folder-viewer = 'icon-view'\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        module,
        "gsettings_set",
        lambda schema, key, value: calls.append((schema, key, value)),
    )

    module.run_apply(input_path)

    assert calls == [
        ("org.gnome.nautilus.icon-view", "default-zoom-level", "'medium'"),
        ("org.gnome.nautilus.preferences", "default-folder-viewer", "'icon-view'"),
    ]


def test_run_apply_resets_keys_marked_with_reset_token(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "desktop.ini"
    input_path.write_text(
        "[org.gnome.desktop.interface]\n"
        "color-scheme = __RESET__\n"
        "icon-theme = 'Papirus-Dark'\n",
        encoding="utf-8",
    )
    reset_calls: list[tuple[str, str]] = []
    set_calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        module,
        "gsettings_reset",
        lambda schema, key: reset_calls.append((schema, key)),
    )
    monkeypatch.setattr(
        module,
        "gsettings_set",
        lambda schema, key, value: set_calls.append((schema, key, value)),
    )

    module.run_apply(input_path)

    assert reset_calls == [("org.gnome.desktop.interface", "color-scheme")]
    assert set_calls == [
        ("org.gnome.desktop.interface", "icon-theme", "'Papirus-Dark'")
    ]

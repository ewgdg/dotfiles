from __future__ import annotations

from pathlib import Path

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

    module.run_dump(template_path, output_path)

    result = module.read_ini(output_path)

    assert list(result["org.gnome.desktop.interface"]) == [
        "icon-theme",
        "gtk-theme",
        "cursor-theme",
    ]


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

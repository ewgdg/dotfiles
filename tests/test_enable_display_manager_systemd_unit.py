from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts/enable_display_manager_systemd_unit.py"
MODULE_SPEC = spec_from_file_location("enable_display_manager_systemd_unit", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
MODULE = module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


def test_extract_aliases_from_unit_text_collects_all_alias_entries() -> None:
    unit_text = """
[Unit]
Description=Example

[Install]
Alias=display-manager.service
Alias=dm.service extra.service
WantedBy=graphical.target
""".lstrip()

    assert MODULE.extract_aliases_from_unit_text(unit_text) == {
        "display-manager.service",
        "dm.service",
        "extra.service",
    }


def test_find_display_manager_units_uses_effective_unit_file_precedence(tmp_path: Path) -> None:
    etc_dir = tmp_path / "etc"
    usr_dir = tmp_path / "usr"
    etc_dir.mkdir()
    usr_dir.mkdir()

    (usr_dir / "greetd.service").write_text(
        """
[Install]
Alias=display-manager.service
""".lstrip(),
        encoding="utf-8",
    )
    (usr_dir / "plain.service").write_text(
        """
[Install]
WantedBy=multi-user.target
""".lstrip(),
        encoding="utf-8",
    )
    # Higher-precedence override without Alias= should win over lower-precedence vendor file.
    (etc_dir / "sddm.service").write_text(
        """
[Install]
WantedBy=graphical.target
""".lstrip(),
        encoding="utf-8",
    )
    (usr_dir / "sddm.service").write_text(
        """
[Install]
Alias=display-manager.service
""".lstrip(),
        encoding="utf-8",
    )

    assert MODULE.find_display_manager_units((etc_dir, usr_dir)) == ("greetd.service",)


def test_select_units_to_disable_skips_keep_unit_and_non_enabled_units() -> None:
    assert MODULE.select_units_to_disable(
        display_manager_units=("greetd.service", "plasmalogin.service", "sddm.service"),
        keep_unit="greetd.service",
        is_enabled=lambda unit_name: unit_name != "sddm.service",
    ) == ("plasmalogin.service",)


def test_print_dry_run_plan_lists_enable_and_disable_actions(capsys) -> None:
    exit_code = MODULE.print_dry_run_plan(
        target_unit="greetd.service",
        enable_target=True,
        units_to_disable=("sddm.service",),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.splitlines() == [
        "enable greetd.service",
        "disable --now sddm.service",
    ]


def test_main_handles_keyboard_interrupt_without_traceback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        MODULE,
        "enable_display_manager_unit",
        lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert MODULE.main(["greetd.service"]) == 130

    captured = capsys.readouterr()
    assert captured.err == "\ninterrupted\n"

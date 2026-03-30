"""Tests for DotManager.parse_args."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dotman import DotManager, ParsedArgs, PendingSelectionItem


def make_manager(operation: str = "update") -> DotManager:
    """Return a DotManager with dotdrop_cmd and operation set for parse_args use."""
    dm = DotManager.__new__(DotManager)
    dm.dotdrop_cmd = "dotdrop"
    dm.operation = operation
    return dm


def test_find_supported_operation_as_first_arg():
    assert DotManager.find_supported_operation(["update", "key1"]) == ("update", 0)


def test_find_supported_operation_after_global_flags():
    assert DotManager.find_supported_operation(["-c", "/tmp/config.yaml", "update", "key1"]) == (
        "update",
        2,
    )


def test_find_supported_operation_after_long_equals_flag():
    assert DotManager.find_supported_operation(["--profile=host", "install"]) == ("install", 1)


def test_find_supported_operation_after_known_boolean_flag():
    assert DotManager.find_supported_operation(["-V", "update", "key1"]) == ("update", 1)


def test_find_supported_operation_ignores_literal_targets_after_double_dash():
    assert DotManager.find_supported_operation(["-f", "--", "update"]) is None


def test_find_supported_operation_stops_at_first_non_option_positional():
    assert DotManager.find_supported_operation(["files", "update"]) is None


def test_find_supported_operation_does_not_scan_past_unknown_flag():
    assert DotManager.find_supported_operation(["--some-dotdrop-only-flag", "update"]) is None


def test_run_detects_operation_when_not_first_arg(monkeypatch: pytest.MonkeyPatch):
    dm = DotManager(["--cfg=/tmp/config.yaml", "update", "key1"])
    dm.dotdrop_cmd = "dotdrop"

    monkeypatch.setattr(dm, "resolve_config_path", lambda: "/tmp/config.yaml")
    monkeypatch.setattr(dm, "resolve_profile", lambda: "host")
    monkeypatch.setattr(dm, "load_dotfiles_output", lambda: "")
    monkeypatch.setattr(dm, "load_key_metadata", lambda _output: None)
    monkeypatch.setattr(dm, "select_targets", lambda: None)
    monkeypatch.setattr(dm, "confirm_update_overwrite_targets", lambda: None)
    monkeypatch.setattr(dm, "run_update_phases", lambda: None)
    monkeypatch.setattr(dm, "restore_declined_update_state", lambda: None)
    monkeypatch.setattr(dm, "run_passthrough", lambda _args: pytest.fail("unexpected passthrough"))

    assert dm.run() == 0
    assert dm.operation == "update"
    assert dm.command_args == ["--cfg=/tmp/config.yaml", "key1"]


# ---------------------------------------------------------------------------
# Basic flag parsing
# ---------------------------------------------------------------------------


def test_empty_args_returns_empty_parsed():
    dm = make_manager()
    result = dm.parse_args([])
    assert result == ParsedArgs()


def test_force_flag_short():
    dm = make_manager()
    result = dm.parse_args(["-f"])
    assert result.force_mode is True
    assert "-f" in result.base_args


def test_force_flag_long():
    dm = make_manager()
    result = dm.parse_args(["--force"])
    assert result.force_mode is True
    assert "-f" in result.base_args


def test_remove_existing_short():
    dm = make_manager()
    result = dm.parse_args(["-R"])
    assert result.remove_existing_mode is True
    assert "-R" in result.base_args


def test_remove_existing_long():
    dm = make_manager()
    result = dm.parse_args(["--remove-existing"])
    assert result.remove_existing_mode is True
    assert "-R" in result.base_args


def test_verbose_forwarded():
    dm = make_manager()
    result = dm.parse_args(["-V"])
    assert "-V" in result.base_args
    # verbose is purely a passthrough; no ParsedArgs field for it
    assert result.force_mode is False


def test_no_banner_forwarded():
    dm = make_manager()
    result = dm.parse_args(["-b"])
    assert "-b" in result.base_args


# ---------------------------------------------------------------------------
# Profile and config args
# ---------------------------------------------------------------------------


def test_profile_short_space_separated():
    dm = make_manager()
    result = dm.parse_args(["-p", "myhost"])
    assert result.profile_from_args == "myhost"
    assert result.profile_was_explicitly_selected is True
    assert "-p" not in result.base_args


def test_profile_long_equals():
    dm = make_manager()
    result = dm.parse_args(["--profile=myhost"])
    assert result.profile_from_args == "myhost"
    assert result.profile_was_explicitly_selected is True
    assert "--profile=myhost" not in result.base_args


def test_cfg_short_space_separated():
    dm = make_manager()
    result = dm.parse_args(["-c", "/tmp/config.yaml"])
    assert result.config_path_from_args == "/tmp/config.yaml"
    assert "-c" not in result.base_args


def test_cfg_long_equals():
    dm = make_manager()
    result = dm.parse_args(["--cfg=/tmp/config.yaml"])
    assert result.config_path_from_args == "/tmp/config.yaml"
    assert "--cfg=/tmp/config.yaml" not in result.base_args


def test_metadata_args_uses_resolved_profile_and_config():
    dm = make_manager()
    dm.resolved_profile = "myhost"
    dm.resolved_config_path = "/tmp/config.yaml"

    assert dm.metadata_args == [
        "--cfg=/tmp/config.yaml",
        "--profile=myhost",
    ]


# ---------------------------------------------------------------------------
# workers and ignore
# ---------------------------------------------------------------------------


def test_workers_short():
    dm = make_manager()
    result = dm.parse_args(["-w", "4"])
    assert "--workers=4" in result.base_args


def test_workers_long_equals():
    dm = make_manager()
    result = dm.parse_args(["--workers=4"])
    assert "--workers=4" in result.base_args


def test_ignore_single():
    dm = make_manager()
    result = dm.parse_args(["-i", "*.bak"])
    assert "*.bak" in result.update_ignore_patterns
    assert "--ignore=*.bak" in result.base_args


def test_ignore_long_equals():
    dm = make_manager()
    result = dm.parse_args(["--ignore=*.bak"])
    assert "*.bak" in result.update_ignore_patterns
    assert "--ignore=*.bak" in result.base_args


def test_ignore_multiple():
    dm = make_manager()
    result = dm.parse_args(["-i", "*.bak", "--ignore=*.swp"])
    assert result.update_ignore_patterns == ["*.bak", "*.swp"]
    assert "--ignore=*.bak" in result.base_args
    assert "--ignore=*.swp" in result.base_args


# ---------------------------------------------------------------------------
# -k/--key: update-mode vs passthrough
# ---------------------------------------------------------------------------


def test_key_flag_in_update_mode_sets_key_mode():
    dm = make_manager(operation="update")
    result = dm.parse_args(["-k"])
    assert result.key_mode is True
    assert "-k" not in result.base_args


def test_key_flag_long_in_update_mode():
    dm = make_manager(operation="update")
    result = dm.parse_args(["--key"])
    assert result.key_mode is True
    assert "-k" not in result.base_args


def test_key_flag_in_install_mode_forwarded_to_dotdrop():
    dm = make_manager(operation="install")
    result = dm.parse_args(["-k"])
    assert result.key_mode is False
    assert "-k" in result.base_args


def test_build_operation_call_forces_install_after_combined_selection() -> None:
    dm = make_manager(operation="install")
    dm.parsed = ParsedArgs()
    dm.resolved_config_path = ""
    dm.resolved_profile = "host"
    dm.used_combined_operation_selection = True

    assert dm.build_operation_call(["f_config"]) == [
        "dotdrop",
        "install",
        "-b",
        "--profile=host",
        "-f",
        "f_config",
    ]


def test_build_operation_call_keeps_install_prompting_without_combined_selection() -> None:
    dm = make_manager(operation="install")
    dm.parsed = ParsedArgs()
    dm.resolved_config_path = ""
    dm.resolved_profile = "host"
    dm.used_combined_operation_selection = False

    assert dm.build_operation_call(["f_config"]) == [
        "dotdrop",
        "install",
        "-b",
        "--profile=host",
        "f_config",
    ]


# ---------------------------------------------------------------------------
# Combined selection parsing
# ---------------------------------------------------------------------------


def test_parse_selection_indexes_returns_empty_for_blank_answer():
    assert DotManager.parse_selection_indexes("", 4) == set()


def test_parse_selection_indexes_supports_numbers_ranges_and_commas():
    assert DotManager.parse_selection_indexes("1, 3-4 6", 6) == {1, 3, 4, 6}


def test_parse_selection_indexes_supports_keep_only_inversion():
    assert DotManager.parse_selection_indexes("^2 4", 5) == {1, 3, 5}


def test_parse_selection_indexes_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="out of range"):
        DotManager.parse_selection_indexes("5", 4)


def test_parse_selection_indexes_rejects_descending_ranges():
    with pytest.raises(ValueError, match="invalid range"):
        DotManager.parse_selection_indexes("4-2", 5)


def test_prompt_for_excluded_items_uses_colored_menu_when_enabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    selection_items = [
        PendingSelectionItem(
            key_name="f_alpha",
            action="install",
            from_path=Path("/repo/alpha.toml"),
            to_path=Path("/home/.config/alpha.toml"),
        )
    ]

    monkeypatch.setattr(DotManager, "colors_enabled", staticmethod(lambda: True))
    monkeypatch.setattr(
        DotManager,
        "prompt",
        staticmethod(lambda message: (print(message, end=""), "")[1]),
    )

    excluded = DotManager.prompt_for_excluded_items(selection_items, operation="install")
    output = capsys.readouterr().out

    assert excluded == set()
    assert "\033[1;34m::\033[0m" in output
    assert "\033[1;36m 1)\033[0m" in output
    assert "\033[1;32m[install]\033[0m" in output
    assert "\033[1mf_alpha\033[0m" in output
    assert "Select items to exclude from install:" in output
    assert "/repo/alpha.toml -> /home/.config/alpha.toml" in output
    assert "Exclude by number or range" in output


def test_prompt_for_excluded_items_keeps_plain_menu_when_colors_disabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    selection_items = [
        PendingSelectionItem(
            key_name="f_alpha",
            action="install",
            from_path=Path("/repo/alpha.toml"),
            to_path=Path("/home/.config/alpha.toml"),
        )
    ]

    monkeypatch.setattr(DotManager, "colors_enabled", staticmethod(lambda: False))
    monkeypatch.setattr(
        DotManager,
        "prompt",
        staticmethod(lambda message: (print(message, end=""), "")[1]),
    )

    DotManager.prompt_for_excluded_items(selection_items, operation="install")
    output = capsys.readouterr().out

    assert output.startswith("Select items to exclude from install:\n")
    assert "  1) [install] f_alpha: /repo/alpha.toml -> /home/.config/alpha.toml\n" in output
    assert "\033[" not in output


def test_log_profile_selection_uses_colored_status_line_when_enabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manager = DotManager(["install"])
    manager.resolved_profile = "host-linux"

    monkeypatch.setattr(DotManager, "colors_enabled", staticmethod(lambda: True))

    manager.log_profile_selection()
    output = capsys.readouterr().out

    assert "\033[1;34mprofile:\033[0m" in output
    assert "\033[1;36mhost-linux\033[0m" in output


def test_print_no_pending_operation_message_uses_colored_status_line_when_enabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manager = DotManager(["install"])
    manager.operation = "install"

    monkeypatch.setattr(DotManager, "colors_enabled", staticmethod(lambda: True))

    manager.print_no_pending_operation_message()
    output = capsys.readouterr().out

    assert "\033[1;32mok:\033[0m" in output
    assert "\033[1mnothing to install\033[0m" in output


def test_exclude_pending_update_items_removes_clean_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = DotManager(["update"])
    manager.operation = "update"
    manager.parsed = ParsedArgs()
    manager.regular_update_keys = ["f_settings"]
    manager.regular_update_key_set = {"f_settings"}
    manager.template_update_keys = ["f_template"]
    manager.template_update_key_set = {"f_template"}

    monkeypatch.setattr(manager, "collect_pending_regular_update_candidates", lambda: [])
    monkeypatch.setattr(manager, "collect_pending_template_update_keys", lambda: [])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    manager.exclude_pending_update_items()

    assert manager.regular_update_keys == []
    assert manager.regular_update_key_set == set()
    assert manager.template_update_keys == []
    assert manager.template_update_key_set == set()


def test_run_prints_nothing_to_install_when_pending_install_keys_are_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dm = DotManager(["install"])
    dm.dotdrop_cmd = "dotdrop"

    monkeypatch.setattr(dm, "resolve_config_path", lambda: "/tmp/config.yaml")
    monkeypatch.setattr(dm, "resolve_profile", lambda: "host")
    monkeypatch.setattr(dm, "load_dotfiles_output", lambda: "")
    monkeypatch.setattr(dm, "load_key_metadata", lambda _output: None)
    monkeypatch.setattr(dm, "select_targets", lambda: None)
    monkeypatch.setattr(dm, "exclude_pending_operation_items", lambda: setattr(dm, "install_keys", []))
    monkeypatch.setattr(dm, "run_install_phases", lambda: pytest.fail("unexpected install run"))
    monkeypatch.setattr(dm, "run_passthrough", lambda _args: pytest.fail("unexpected passthrough"))

    assert dm.run() == 0
    output = capsys.readouterr().out
    assert "profile: host" in output
    assert "nothing to install" in output


def test_run_prints_nothing_to_update_when_pending_update_keys_are_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dm = DotManager(["update"])
    dm.dotdrop_cmd = "dotdrop"

    monkeypatch.setattr(dm, "resolve_config_path", lambda: "/tmp/config.yaml")
    monkeypatch.setattr(dm, "resolve_profile", lambda: "host")
    monkeypatch.setattr(dm, "load_dotfiles_output", lambda: "")
    monkeypatch.setattr(dm, "load_key_metadata", lambda _output: None)
    monkeypatch.setattr(dm, "select_targets", lambda: None)
    monkeypatch.setattr(
        dm,
        "exclude_pending_operation_items",
        lambda: (
            setattr(dm, "regular_update_keys", []),
            setattr(dm, "regular_update_key_set", set()),
            setattr(dm, "template_update_keys", []),
            setattr(dm, "template_update_key_set", set()),
        ),
    )
    monkeypatch.setattr(dm, "confirm_update_overwrite_targets", lambda: None)
    monkeypatch.setattr(dm, "run_update_phases", lambda: pytest.fail("unexpected update run"))
    monkeypatch.setattr(dm, "restore_declined_update_state", lambda: None)
    monkeypatch.setattr(dm, "run_passthrough", lambda _args: pytest.fail("unexpected passthrough"))

    assert dm.run() == 0
    output = capsys.readouterr().out
    assert "profile: host" in output
    assert "nothing to update" in output


# ---------------------------------------------------------------------------
# -- separator: literal targets
# ---------------------------------------------------------------------------


def test_double_dash_separates_literal_targets():
    dm = make_manager()
    result = dm.parse_args(["-f", "--", "target1", "target2"])
    assert result.force_mode is True
    assert result.explicit_targets == ["target1", "target2"]


def test_double_dash_target_starting_with_dash_not_parsed_as_flag():
    dm = make_manager()
    result = dm.parse_args(["--", "-f"])
    assert result.force_mode is False
    assert "-f" in result.explicit_targets


def test_positional_args_become_explicit_targets():
    dm = make_manager()
    result = dm.parse_args(["dotfile_key1", "dotfile_key2"])
    assert result.explicit_targets == ["dotfile_key1", "dotfile_key2"]


def test_mixed_flags_and_targets():
    dm = make_manager()
    result = dm.parse_args(["-f", "key1", "--profile=host"])
    assert result.force_mode is True
    assert result.profile_from_args == "host"
    assert "key1" in result.explicit_targets


# ---------------------------------------------------------------------------
# Combined short flags (argparse handles natively)
# ---------------------------------------------------------------------------


def test_combined_short_flags_fV():
    dm = make_manager()
    result = dm.parse_args(["-fV"])
    assert result.force_mode is True
    assert "-V" in result.base_args


def test_combined_short_flags_fR():
    dm = make_manager()
    result = dm.parse_args(["-fR"])
    assert result.force_mode is True
    assert result.remove_existing_mode is True


# ---------------------------------------------------------------------------
# Unknown flags are forwarded to dotdrop
# ---------------------------------------------------------------------------


def test_unknown_flag_forwarded_to_base_args():
    dm = make_manager()
    result = dm.parse_args(["--some-dotdrop-only-flag"])
    assert "--some-dotdrop-only-flag" in result.base_args
    assert result.explicit_targets == []


def test_unknown_short_flag_forwarded():
    dm = make_manager()
    result = dm.parse_args(["-x"])
    assert "-x" in result.base_args


# ---------------------------------------------------------------------------

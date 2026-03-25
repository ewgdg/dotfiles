"""Tests for DotManager.parse_args and DotManager.files_args."""
from __future__ import annotations

import pytest

from scripts.dotman import DotManager, ParsedArgs


def make_manager(operation: str = "update") -> DotManager:
    """Return a DotManager with dotdrop_cmd and operation set for parse_args use."""
    dm = DotManager.__new__(DotManager)
    dm.dotdrop_cmd = "dotdrop"
    dm.operation = operation
    return dm


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
    assert "--profile=myhost" in result.base_args
    # Must be a single token — no bare "-p" in base_args
    assert "-p" not in result.base_args


def test_profile_long_equals():
    dm = make_manager()
    result = dm.parse_args(["--profile=myhost"])
    assert result.profile_from_args == "myhost"
    assert result.profile_was_explicitly_selected is True
    assert "--profile=myhost" in result.base_args


def test_cfg_short_space_separated():
    dm = make_manager()
    result = dm.parse_args(["-c", "/tmp/config.yaml"])
    assert result.config_path_from_args == "/tmp/config.yaml"
    assert "--cfg=/tmp/config.yaml" in result.base_args
    assert "-c" not in result.base_args


def test_cfg_long_equals():
    dm = make_manager()
    result = dm.parse_args(["--cfg=/tmp/config.yaml"])
    assert result.config_path_from_args == "/tmp/config.yaml"
    assert "--cfg=/tmp/config.yaml" in result.base_args


def test_files_args_only_returns_profile_and_cfg():
    """files_args must include profile/cfg tokens and nothing else."""
    dm = make_manager()
    dm.parsed = dm.parse_args(["-f", "--profile=myhost", "--cfg=/tmp/c.yaml", "-V"])
    result = dm.files_args
    assert "--profile=myhost" in result
    assert "--cfg=/tmp/c.yaml" in result
    assert "-f" not in result
    assert "-V" not in result


def test_files_args_empty_when_no_profile_or_cfg():
    dm = make_manager()
    dm.parsed = dm.parse_args(["-f", "-V"])
    assert dm.files_args == []


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
# files_args: regression test for the two-token bug
# ---------------------------------------------------------------------------


def test_files_args_never_returns_bare_p_flag():
    """Regression: space-separated -p VALUE must not produce a bare '-p' token."""
    dm = make_manager()
    dm.parsed = dm.parse_args(["-p", "host"])
    for token in dm.files_args:
        assert token != "-p", "bare '-p' without value must not appear in files_args"
        assert token != "--profile", "bare '--profile' without value must not appear in files_args"


def test_files_args_never_returns_bare_c_flag():
    """Regression: space-separated -c VALUE must not produce a bare '-c' token."""
    dm = make_manager()
    dm.parsed = dm.parse_args(["-c", "/some/path.yaml"])
    for token in dm.files_args:
        assert token != "-c", "bare '-c' without value must not appear in files_args"
        assert token != "--cfg", "bare '--cfg' without value must not appear in files_args"

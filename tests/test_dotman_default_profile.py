from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DOTMAN_PATH = REPO_ROOT / "dotfiles" / "bin" / "dotman"
DOTMAN_PY_PATH = REPO_ROOT / "scripts" / "dotman.py"

DOTMAN_SPEC = importlib.util.spec_from_file_location("dotman_py", DOTMAN_PY_PATH)
assert DOTMAN_SPEC is not None
assert DOTMAN_SPEC.loader is not None
DOTMAN_MODULE = importlib.util.module_from_spec(DOTMAN_SPEC)
sys.modules[DOTMAN_SPEC.name] = DOTMAN_MODULE
DOTMAN_SPEC.loader.exec_module(DOTMAN_MODULE)
DotManager = DOTMAN_MODULE.DotManager


# --- Profile graph height tests ---


SAMPLE_PROFILES = {
    "apps_base": {},
    "toolchain_javascript": {},
    "toolchain_rust": {},
    "framework_gtk": {},
    "de_gnome": {},
    "de_kde": {},
    "de_hypr": {},
    "de_niri": {},
    "apps_linux": {},
    "apps_mac": {},
    "apps_ai": {},
    "os_arch_kernel": {},
    "posix_utils": {},
    "base": {"include": ["apps_base"]},
    "posix_base": {"include": ["base", "toolchain_javascript", "toolchain_rust"]},
    "os_linux": {"include": ["posix_base", "posix_utils", "framework_gtk"]},
    "os_mac": {"include": ["posix_base", "posix_utils"]},
    "os_arch": {"include": ["os_linux"]},
    "xian-linux-server": {"include": ["os_arch", "de_niri", "de_kde", "apps_linux", "apps_ai"]},
    "xian-macbook-air.local": {"include": ["os_mac", "apps_mac", "apps_ai"]},
}


def test_compute_profile_heights_returns_correct_heights() -> None:
    heights = DOTMAN_MODULE.compute_profile_heights(SAMPLE_PROFILES)

    assert heights["apps_base"] == 0
    assert heights["toolchain_javascript"] == 0
    assert heights["de_niri"] == 0
    assert heights["base"] == 1
    assert heights["posix_base"] == 2
    assert heights["os_linux"] == 3
    assert heights["os_mac"] == 3
    assert heights["os_arch"] == 4
    assert heights["xian-linux-server"] == 5
    assert heights["xian-macbook-air.local"] == 4


def test_compute_profile_heights_handles_empty_profiles() -> None:
    heights = DOTMAN_MODULE.compute_profile_heights({})
    assert heights == {}


def test_compute_profile_heights_handles_single_profile() -> None:
    heights = DOTMAN_MODULE.compute_profile_heights({"solo": {}})
    assert heights == {"solo": 0}


def test_compute_profile_heights_handles_missing_include_target() -> None:
    """If a profile includes a name that doesn't exist, treat it as height 0."""
    profiles = {
        "parent": {"include": ["ghost"]},
    }
    heights = DOTMAN_MODULE.compute_profile_heights(profiles)
    assert heights["parent"] == 1


# --- Rank profiles tests ---


def test_rank_profiles_top_nodes_come_first() -> None:
    ranked = DOTMAN_MODULE.rank_profiles(SAMPLE_PROFILES)

    # Top nodes (not included by anyone) should appear before non-top nodes
    top_node_names = {"xian-linux-server", "xian-macbook-air.local", "os_arch_kernel", "de_gnome", "de_hypr"}
    non_top_indices = []
    top_indices = []
    for idx, name in enumerate(ranked):
        if name in top_node_names:
            top_indices.append(idx)
        else:
            non_top_indices.append(idx)

    if top_indices and non_top_indices:
        assert max(top_indices) < min(non_top_indices), (
            f"All top nodes should come before non-top nodes: {ranked}"
        )


def test_rank_profiles_top_nodes_sorted_by_height_desc() -> None:
    ranked = DOTMAN_MODULE.rank_profiles(SAMPLE_PROFILES)

    # Among top nodes, higher height should come first
    top_nodes = [p for p in ranked if p in {"xian-linux-server", "xian-macbook-air.local", "os_arch_kernel", "de_gnome", "de_hypr"}]
    assert top_nodes[0] == "xian-linux-server"   # height 5
    assert top_nodes[1] == "xian-macbook-air.local"  # height 4


def test_rank_profiles_within_same_tier_sorted_by_height_then_name() -> None:
    ranked = DOTMAN_MODULE.rank_profiles(SAMPLE_PROFILES)

    # Within non-top nodes, os_arch (height 4) should come before os_linux (height 3)
    non_top = [p for p in ranked if p not in {"xian-linux-server", "xian-macbook-air.local", "os_arch_kernel", "de_gnome", "de_hypr"}]
    assert non_top.index("os_arch") < non_top.index("os_linux")
    assert non_top.index("os_linux") < non_top.index("base")


# --- Default profile state file tests ---


def test_read_default_profile_returns_empty_when_no_file(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "dotman"
    result = DOTMAN_MODULE.read_default_profile(state_dir)
    assert result == ""


def test_write_and_read_default_profile(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "dotman"
    DOTMAN_MODULE.write_default_profile(state_dir, "xian-linux-server")
    assert DOTMAN_MODULE.read_default_profile(state_dir) == "xian-linux-server"


def test_unset_default_profile(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "dotman"
    DOTMAN_MODULE.write_default_profile(state_dir, "xian-linux-server")
    assert DOTMAN_MODULE.read_default_profile(state_dir) == "xian-linux-server"

    DOTMAN_MODULE.unset_default_profile(state_dir)
    assert DOTMAN_MODULE.read_default_profile(state_dir) == ""


def test_unset_default_profile_noop_when_no_file(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "dotman"
    # Should not raise
    DOTMAN_MODULE.unset_default_profile(state_dir)
    assert DOTMAN_MODULE.read_default_profile(state_dir) == ""


def test_read_default_profile_ignores_whitespace(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "dotman"
    state_dir.mkdir(parents=True)
    (state_dir / "default-profile").write_text("  my-profile  \n\n", encoding="utf-8")
    assert DOTMAN_MODULE.read_default_profile(state_dir) == "my-profile"


# --- resolve_profile precedence tests ---


def test_resolve_profile_prefers_cli_over_stored_default(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state" / "dotman"
    DOTMAN_MODULE.write_default_profile(state_dir, "stored-profile")

    manager = DotManager(["install", "-p", "cli-profile"])
    manager.parsed.profile_from_args = "cli-profile"
    monkeypatch.setattr(DOTMAN_MODULE, "get_dotman_state_dir", lambda: state_dir)
    monkeypatch.delenv("DOTDROP_PROFILE", raising=False)

    result = manager.resolve_profile()

    assert result == "cli-profile"


def test_resolve_profile_prefers_env_over_stored_default(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state" / "dotman"
    DOTMAN_MODULE.write_default_profile(state_dir, "stored-profile")

    manager = DotManager(["install"])
    monkeypatch.setattr(DOTMAN_MODULE, "get_dotman_state_dir", lambda: state_dir)
    monkeypatch.setenv("DOTDROP_PROFILE", "env-profile")

    result = manager.resolve_profile()

    assert result == "env-profile"


def test_resolve_profile_uses_stored_default_when_no_cli_or_env(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state" / "dotman"
    DOTMAN_MODULE.write_default_profile(state_dir, "stored-profile")

    manager = DotManager(["install"])
    monkeypatch.setattr(DOTMAN_MODULE, "get_dotman_state_dir", lambda: state_dir)
    monkeypatch.delenv("DOTDROP_PROFILE", raising=False)

    result = manager.resolve_profile()

    assert result == "stored-profile"


def test_resolve_profile_returns_empty_when_no_source_exists(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state" / "dotman"

    manager = DotManager(["install"])
    monkeypatch.setattr(DOTMAN_MODULE, "get_dotman_state_dir", lambda: state_dir)
    monkeypatch.delenv("DOTDROP_PROFILE", raising=False)

    result = manager.resolve_profile()

    assert result == ""

# --- parse_profiles_from_config tests ---


def test_parse_profiles_from_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join([
            "config:",
            "  dotpath: dotfiles",
            "dotfiles:",
            "  f_zshrc:",
            "    src: zshrc",
            "    dst: ~/.zshrc",
            "profiles:",
            "  base:",
            "    dotfiles:",
            "    - f_zshrc",
            "  child:",
            "    include:",
            "    - base",
            "    dotfiles:",
            "    - f_zshrc",
            "",
        ]),
        encoding="utf-8",
    )
    profiles = DOTMAN_MODULE.parse_profiles_from_config(str(config_path))
    assert "base" in profiles
    assert "child" in profiles
    assert profiles["child"]["include"] == ["base"]

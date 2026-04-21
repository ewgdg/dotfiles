from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "packages/shell/files/profile"
ZSHENV_PATH = REPO_ROOT / "packages/shell/files/zshenv"


def test_profile_skips_core_env_source_when_running_under_zsh() -> None:
    profile_text = PROFILE_PATH.read_text(encoding="utf-8")

    assert 'if [ -z "${ZSH_VERSION:-}" ]; then' in profile_text
    assert '. "$dotfiles_core_env_path"' in profile_text


def test_zshenv_sources_deployed_core_env_for_all_zsh_shells() -> None:
    zshenv_text = ZSHENV_PATH.read_text(encoding="utf-8")

    assert 'dotfiles_core_env_path="$HOME/.config/shell/env.core.sh"' in zshenv_text
    assert '. "$dotfiles_core_env_path"' in zshenv_text

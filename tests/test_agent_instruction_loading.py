from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SYMLINK_HELPER = REPO_ROOT / "scripts/manage_relative_symlink.sh"
def run_helper(
    mode: str,
    destination: str | Path,
    expected: str,
    *,
    home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if home is not None:
        environment["HOME"] = str(home)

    return subprocess.run(
        ["sh", str(SYMLINK_HELPER), mode, str(destination), expected],
        capture_output=True,
        text=True,
        env=environment,
    )


def test_symlink_probe_expands_home_and_distinguishes_exact_raw_payload(tmp_path: Path) -> None:
    home = tmp_path / "home"
    destination = home / ".codex" / "AGENTS.md"
    destination_spec = "~/.codex/AGENTS.md"
    expected = home / ".agents" / "AGENTS.md"

    assert run_helper("probe", destination_spec, "~/.agents/AGENTS.md", home=home).returncode == 0

    destination.parent.mkdir(parents=True)
    destination.symlink_to(expected)
    assert run_helper("probe", destination_spec, "~/.agents/AGENTS.md", home=home).returncode == 100
    assert run_helper("probe", destination_spec, "$HOME/.agents/AGENTS.md", home=home).returncode == 100
    assert run_helper("probe", destination_spec, "${HOME}/.agents/AGENTS.md", home=home).returncode == 100

    destination.unlink()
    destination.symlink_to(home / ".agents" / "other.md")
    assert run_helper("probe", destination_spec, "~/.agents/AGENTS.md", home=home).returncode == 0

    destination.unlink()
    destination.write_text("not a symlink")
    assert run_helper("probe", destination_spec, "~/.agents/AGENTS.md", home=home).returncode == 0

    destination.unlink()
    destination.mkdir()
    assert run_helper("probe", destination_spec, "~/.agents/AGENTS.md", home=home).returncode not in (0, 100)


def test_symlink_helper_rejects_unexpanded_relative_target(tmp_path: Path) -> None:
    completed = run_helper("probe", tmp_path / "AGENTS.md", "../.agents/AGENTS.md")

    assert completed.returncode not in (0, 100)


def test_symlink_probe_hard_fails_when_parent_cannot_be_inspected(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root bypasses directory search permissions")

    parent = tmp_path / "inaccessible"
    parent.mkdir()
    parent.chmod(0)
    try:
        completed = run_helper("probe", parent / "AGENTS.md", "../.agents/AGENTS.md")
    finally:
        parent.chmod(0o700)

    assert completed.returncode not in (0, 100)


def test_symlink_apply_creates_replaces_and_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    destination = home / ".claude" / "rules" / "global.md"
    destination_spec = "~/.claude/rules/global.md"
    expected = home / ".agents" / "AGENTS.md"

    assert run_helper("apply", destination_spec, "~/.agents/AGENTS.md", home=home).returncode == 0
    assert destination.is_symlink()
    assert os.readlink(destination) == str(expected)

    first_inode = destination.lstat().st_ino
    assert run_helper("apply", destination_spec, "$HOME/.agents/AGENTS.md", home=home).returncode == 0
    assert destination.lstat().st_ino == first_inode

    destination.unlink()
    destination.write_text("replace me")
    assert run_helper("apply", destination_spec, "${HOME}/.agents/AGENTS.md", home=home).returncode == 0
    assert os.readlink(destination) == str(expected)

    destination.unlink()
    destination.symlink_to("wrong-target")
    assert run_helper("apply", destination_spec, "~/.agents/AGENTS.md", home=home).returncode == 0
    assert os.readlink(destination) == str(expected)


def test_symlink_apply_refuses_to_replace_directory(tmp_path: Path) -> None:
    destination = tmp_path / "AGENTS.md"
    destination.mkdir()

    completed = run_helper("apply", destination, "../.agents/AGENTS.md")

    assert completed.returncode not in (0, 100)
    assert destination.is_dir()


@pytest.mark.parametrize(
    ("package", "target", "destination", "payload"),
    [
        ("claude", "claude_global_instructions", "~/.claude/rules/global.md", "~/.agents/AGENTS.md"),
        ("codex", "codex_global_instructions", "~/.codex/AGENTS.md", "~/.agents/AGENTS.md"),
    ],
)
def test_agent_manifests_use_independent_push_only_symlink_targets(
    package: str,
    target: str,
    destination: str,
    payload: str,
) -> None:
    manifest = tomllib.loads((REPO_ROOT / "packages" / package / "package.toml").read_text())

    assert "agents" in manifest["depends"]
    target_config = manifest["targets"][target]
    assert target_config["sync_policy"] == "push-only"
    assert "source" not in target_config
    assert "path" not in target_config
    assert target_config["probe"] == (
        f'sh "$DOTMAN_REPO_ROOT/scripts/manage_relative_symlink.sh" probe '
        f'"{destination}" "{payload}"'
    )
    assert target_config["hooks"]["pre_push"] == (
        f'sh "$DOTMAN_REPO_ROOT/scripts/manage_relative_symlink.sh" apply '
        f'"{destination}" "{payload}"'
    )


def test_agent_import_wrappers_and_codex_developer_instructions_are_removed() -> None:
    config = tomllib.loads((REPO_ROOT / "packages/codex/files/codex/config.toml").read_text())

    assert "developer_instructions" not in config
    assert not (REPO_ROOT / "packages/codex/files/codex/AGENTS.md").exists()
    assert not (REPO_ROOT / "packages/codex/files/codex/AGENTS.codex.md").exists()
    assert not (REPO_ROOT / "packages/claude/files/claude/CLAUDE.md").exists()


def test_zsh_uses_normal_codex_resolution_without_expansion_helper() -> None:
    agents_zsh = (REPO_ROOT / "packages/shell/files/config/zsh/agents.zsh").read_text()

    assert "codex()" not in agents_zsh
    assert "agents-file-expand.py" not in agents_zsh
    assert "claudex()" in agents_zsh
    assert not (REPO_ROOT / "packages/shell/files/config/zsh/helpers/agents-file-expand.py").exists()


def test_claudex_uses_the_cross_device_https_endpoint() -> None:
    agents_zsh = (REPO_ROOT / "packages/shell/files/config/zsh/agents.zsh").read_text()

    assert 'ANTHROPIC_BASE_URL="https://cliproxyapi.service.xianzzz.com"' in agents_zsh

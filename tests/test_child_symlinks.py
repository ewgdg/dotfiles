from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
CHILD_SYMLINK_HELPER = REPO_ROOT / "scripts/manage_child_symlinks.sh"
WORK_NEEDED = 0
CURRENT = 100


def run_helper(mode: str, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(CHILD_SYMLINK_HELPER), mode, "~/.claude/skills", "~/.agents/skills"],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )


def make_home(tmp_path: Path, *skills: str) -> Path:
    home = tmp_path / "home"
    (home / ".agents/skills").mkdir(parents=True)
    for skill in skills:
        (home / ".agents/skills" / skill).mkdir()
    return home


def linked_skills(home: Path) -> dict[str, str]:
    destination = home / ".claude/skills"
    return {entry.name: os.readlink(entry) for entry in destination.iterdir() if entry.is_symlink()}


def test_apply_links_each_skill_and_probe_reports_current(tmp_path: Path) -> None:
    home = make_home(tmp_path, "tdd", "surf")

    assert run_helper("probe", home).returncode == WORK_NEEDED
    assert run_helper("apply", home).returncode == 0

    source = home / ".agents/skills"
    assert linked_skills(home) == {"tdd": str(source / "tdd"), "surf": str(source / "surf")}
    assert run_helper("probe", home).returncode == CURRENT
    assert run_helper("apply", home).returncode == 0


def test_removed_skill_link_is_pruned_but_foreign_entries_are_kept(tmp_path: Path) -> None:
    home = make_home(tmp_path, "tdd", "surf")
    run_helper("apply", home)
    destination = home / ".claude/skills"
    (destination / "synced/account-skill").mkdir(parents=True)
    (destination / "manual").symlink_to(tmp_path / "elsewhere")
    (home / ".agents/skills/surf").rmdir()

    assert run_helper("probe", home).returncode == WORK_NEEDED
    assert run_helper("apply", home).returncode == 0

    assert linked_skills(home) == {
        "tdd": str(home / ".agents/skills/tdd"),
        "manual": str(tmp_path / "elsewhere"),
    }
    assert (destination / "synced/account-skill").is_dir()
    assert run_helper("probe", home).returncode == CURRENT


def test_symlinked_skill_is_linked_by_its_source_path(tmp_path: Path) -> None:
    home = make_home(tmp_path)
    (tmp_path / "external/tdd").mkdir(parents=True)
    (home / ".agents/skills/tdd").symlink_to(tmp_path / "external/tdd")

    run_helper("apply", home)

    assert linked_skills(home) == {"tdd": str(home / ".agents/skills/tdd")}


def test_hidden_source_entries_are_not_linked(tmp_path: Path) -> None:
    home = make_home(tmp_path, "tdd")
    (home / ".agents/skills/.DS_Store").write_text("")

    run_helper("apply", home)

    assert set(linked_skills(home)) == {"tdd"}


def test_conflicting_destination_entry_fails_without_replacement(tmp_path: Path) -> None:
    home = make_home(tmp_path, "tdd")
    conflict = home / ".claude/skills/tdd"
    conflict.mkdir(parents=True)

    for mode in ("probe", "apply"):
        completed = run_helper(mode, home)
        assert completed.returncode not in (WORK_NEEDED, CURRENT)
        assert str(conflict) in completed.stderr
    assert conflict.is_dir() and not conflict.is_symlink()


def test_symlinked_destination_directory_fails_without_writing_into_source(tmp_path: Path) -> None:
    home = make_home(tmp_path, "tdd")
    (home / ".claude").mkdir()
    (home / ".claude/skills").symlink_to(home / ".agents/skills")

    for mode in ("probe", "apply"):
        completed = run_helper(mode, home)
        assert completed.returncode not in (WORK_NEEDED, CURRENT)
        assert "destination directory is a symlink" in completed.stderr
    assert not (home / ".agents/skills/tdd/tdd").exists()


def test_claude_manifest_links_skills_after_push() -> None:
    manifest = tomllib.loads((REPO_ROOT / "packages/claude/package.toml").read_text())
    target = manifest["targets"]["claude_skills_link"]
    arguments = '"~/.claude/skills" "~/.agents/skills"'

    assert target["sync_policy"] == "push-only"
    assert target["probe"] == f'sh "$DOTMAN_REPO_ROOT/scripts/manage_child_symlinks.sh" probe {arguments}'
    assert target["hooks"] == {
        "post_push": f'sh "$DOTMAN_REPO_ROOT/scripts/manage_child_symlinks.sh" apply {arguments}',
    }

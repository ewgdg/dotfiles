"""Validate definitions without planning live operations or running hooks."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = Path(os.environ.get("DOTMAN_CANDIDATE_ROOT", REPO_ROOT.parent / "dotman"))


@pytest.mark.skipif(not (CANDIDATE_ROOT / "pyproject.toml").is_file(), reason="candidate dotman checkout unavailable")
def test_catalog_loads_and_resolves_with_dotman(tmp_path: Path) -> None:
    script = """
import sys
from pathlib import Path
from dotman.models import RepoConfig
from dotman.repository import Repository

root, scratch = map(Path, sys.argv[1:])
repo = Repository(RepoConfig(
    name="main", path=root, order=10, state_key="main",
    state_path=scratch / "state", local_override_path=scratch / "local.toml",
))
for package_id in repo.packages:
    repo.resolve_package(package_id)
for group_id in repo.groups:
    for package_id in repo.expand_group(group_id):
        repo.resolve_package(package_id)
for profile_id in repo.profiles:
    repo.compose_profile(profile_id)
print(f"{len(repo.packages)} packages, {len(repo.groups)} groups, {len(repo.profiles)} profiles")
"""
    completed = subprocess.run(
        ["uv", "run", "--project", str(CANDIDATE_ROOT), "python", "-c", script,
         str(REPO_ROOT), str(tmp_path)],
        capture_output=True, text=True, timeout=5, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "packages" in completed.stdout

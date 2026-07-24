from __future__ import annotations

from pathlib import Path
import subprocess
import tomllib

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "script_relative_path",
    [
        "packages/goldendict/scripts/sync_goldendict_config.py",
        "packages/greetd/scripts/capture_greetd_config.py",
        "packages/greetd/scripts/render_greetd_config.py",
        "packages/greetd/scripts/validate_greetd_start_session.py",
        "packages/gsettings/scripts/gsettings_sync.py",
        "packages/linux/avahi/scripts/render_avahi_daemon_conf.py",
        "packages/gsettings/scripts/sync_gsettings_gtk.py",
        "scripts/enable_display_manager_systemd_unit.py",
        "scripts/kv_transform.py",
    ],
)
def test_script_runs_via_uv_project_from_outside_repo(
    tmp_path: Path,
    script_relative_path: str,
) -> None:
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            str(REPO_ROOT / script_relative_path),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "usage:" in completed.stdout


@pytest.mark.parametrize("action", ["expand", "collapse"])
def test_dotman_home_rewrite_command_is_available_from_outside_repo(
    action: str,
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        ["dotman", "rewrite", "home", action, "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    assert f"usage: dotman rewrite home {action}" in completed.stdout


def test_dotfiles_tools_does_not_depend_on_dotman_python_package() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as project_file:
        dependencies = tomllib.load(project_file)["project"]["dependencies"]

    assert all(not dependency.casefold().startswith("dotman") for dependency in dependencies)

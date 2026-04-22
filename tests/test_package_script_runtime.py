from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "script_relative_path",
    [
        "packages/goldendict/scripts/sync_goldendict_config.py",
        "packages/greetd/scripts/capture_greetd_config.py",
        "packages/greetd/scripts/render_greetd_config.py",
        "packages/gsettings/scripts/gsettings_sync.py",
        "packages/gsettings/scripts/sync_gsettings_gtk.py",
        "scripts/enable_display_manager_systemd_unit.py",
        "scripts/xml_transform.py",
        "scripts/toml_transform.py",
        "scripts/plist_transform.py",
        "scripts/json_transform.py",
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


def test_transform_cli_imports_via_uv_project_from_outside_repo(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            "python",
            "-c",
            "import scripts.transform_cli; print('ok')",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "ok"

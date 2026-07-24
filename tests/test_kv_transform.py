from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import kv_transform as module


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/kv_transform.py"


def test_capture_removes_keys_and_collapses_selected_home_values(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")

    captured = module.capture_config_text(
        'close-onlaunch=False\n'
        'default-prefix="/home/tester/Games/prefixes"\n'
        'playtime=42\n'
        'donate-last=2026-05\n'
        'notes="/home/tester/must-stay-absolute"\n'
        'system-tray=True\n',
        remove_keys={"donate-last", "playtime"},
        home_collapse_keys={"default-prefix"},
        require_keys={"default-prefix"},
    )

    assert 'default-prefix="~/Games/prefixes"' in captured
    assert "playtime=" not in captured
    assert "donate-last=" not in captured
    assert 'notes="/home/tester/must-stay-absolute"' in captured
    assert "system-tray=True" in captured


def test_render_expands_selected_home_values_and_preserves_live_unknown_keys(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")

    rendered = module.render_config_text(
        'default-prefix="~/Games/prefixes"\n'
        'system-tray=True\n',
        live_text=(
            'default-prefix="/home/tester/Faugus"\n'
            'system-tray=False\n'
            'playtime=42\n'
            'future-key=/home/tester/must-stay-absolute\n'
        ),
        home_expand_keys={"default-prefix"},
        require_keys={"default-prefix"},
    )

    assert 'default-prefix="/home/tester/Games/prefixes"' in rendered
    assert "system-tray=True" in rendered
    assert "playtime=42" in rendered
    assert "future-key=/home/tester/must-stay-absolute" in rendered


def test_render_without_live_file_outputs_repo_keys_with_expanded_home_values(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")

    rendered = module.render_config_text(
        'default-prefix="~/Games/prefixes"\n'
        'system-tray=True\n',
        home_expand_keys={"default-prefix"},
        require_keys={"default-prefix"},
    )

    assert rendered == 'default-prefix="/home/tester/Games/prefixes"\nsystem-tray=True\n'


def test_comment_lines_with_equals_are_not_treated_as_keys(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")

    rendered = module.render_config_text(
        '# default-prefix="~/ignored"\n'
        '; other-key=value\n'
        'default-prefix="~/Games/prefixes"\n',
        home_expand_keys={"default-prefix"},
        require_keys={"default-prefix"},
    )

    assert rendered == (
        '# default-prefix="~/ignored"\n'
        '; other-key=value\n'
        'default-prefix="/home/tester/Games/prefixes"\n'
    )


def test_selected_home_values_are_rewritten_through_public_dotman_cli(monkeypatch) -> None:
    observed_calls: list[tuple[list[str], str]] = []

    def fake_run(command, **kwargs):
        input_value = kwargs["input"]
        observed_calls.append((command, input_value))
        action = command[3]
        if action == "expand":
            output = input_value.replace("~/", "/home/tester/")
        else:
            output = input_value.replace("/home/tester/", "~/")
        return subprocess.CompletedProcess(command, 0, stdout=output)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rendered = module.render_config_text(
        'default-prefix="~/Games/prefixes"\nnotes="~/must-stay-portable"\n',
        home_expand_keys={"default-prefix"},
    )
    captured = module.capture_config_text(
        'default-prefix="/home/tester/Games/prefixes"\n'
        'notes="/home/tester/must-stay-absolute"\n',
        home_collapse_keys={"default-prefix"},
    )

    assert rendered == (
        'default-prefix="/home/tester/Games/prefixes"\nnotes="~/must-stay-portable"\n'
    )
    assert captured == (
        'default-prefix="~/Games/prefixes"\n'
        'notes="/home/tester/must-stay-absolute"\n'
    )
    assert observed_calls == [
        (["dotman", "rewrite", "home", "expand", "-"], "~/Games/prefixes"),
        (["dotman", "rewrite", "home", "collapse", "-"], "/home/tester/Games/prefixes"),
    ]


def test_required_keys_must_exist() -> None:
    with pytest.raises(ValueError, match="missing required keys: default-prefix"):
        module.render_config_text(
            "system-tray=True\n",
            home_expand_keys={"default-prefix"},
            require_keys={"default-prefix"},
        )


def test_cli_capture_accepts_required_home_collapse_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    live_path = tmp_path / "config.ini"
    live_path.write_text(
        'default-prefix="/home/tester/Games/prefixes"\n'
        'notes="/home/tester/must-stay-absolute"\n'
        'playtime=42\n',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "capture",
            str(live_path),
            "--remove-keys",
            "playtime",
            "--home-collapse-keys",
            "default-prefix",
            "--require-keys",
            "default-prefix",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout == (
        'default-prefix="~/Games/prefixes"\n'
        'notes="/home/tester/must-stay-absolute"\n'
    )


def test_cli_render_accepts_missing_live_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    repo_path = tmp_path / "config.ini"
    repo_path.write_text(
        'default-prefix="~/Games/prefixes"\nnotes="~/must-stay-portable"\n',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "render",
            str(repo_path),
            "--live-path",
            str(tmp_path / "missing"),
            "--home-expand-keys",
            "default-prefix",
            "--require-keys",
            "default-prefix",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout == (
        'default-prefix="/home/tester/Games/prefixes"\nnotes="~/must-stay-portable"\n'
    )


def test_cli_reports_missing_dotman_without_traceback(tmp_path: Path) -> None:
    repo_path = tmp_path / "config.ini"
    repo_path.write_text('default-prefix="~/Games/prefixes"\n', encoding="utf-8")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "render",
            str(repo_path),
            "--home-expand-keys",
            "default-prefix",
        ],
        env={**os.environ, "PATH": str(empty_bin)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "kv_transform: dotman executable not found on PATH\n"


def test_cli_propagates_dotman_rewrite_failure(tmp_path: Path) -> None:
    repo_path = tmp_path / "config.ini"
    repo_path.write_text('default-prefix="~/Games/prefixes"\n', encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_dotman = fake_bin / "dotman"
    fake_dotman.write_text(
        "#!/bin/sh\nprintf 'dotman rewrite failed\\n' >&2\nexit 23\n",
        encoding="utf-8",
    )
    fake_dotman.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "render",
            str(repo_path),
            "--home-expand-keys",
            "default-prefix",
        ],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 23
    assert completed.stdout == ""
    assert completed.stderr == "dotman rewrite failed\n"

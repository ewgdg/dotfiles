from __future__ import annotations

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
        'system-tray=True\n',
        remove_keys={"donate-last", "playtime"},
        home_collapse_keys={"default-prefix"},
        require_keys={"default-prefix"},
    )

    assert 'default-prefix="~/Games/prefixes"' in captured
    assert "playtime=" not in captured
    assert "donate-last=" not in captured
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
            'future-key=keep-me\n'
        ),
        home_expand_keys={"default-prefix"},
        require_keys={"default-prefix"},
    )

    assert 'default-prefix="/home/tester/Games/prefixes"' in rendered
    assert "system-tray=True" in rendered
    assert "playtime=42" in rendered
    assert "future-key=keep-me" in rendered


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
        'default-prefix="/home/tester/Games/prefixes"\nplaytime=42\n',
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

    assert completed.stdout == 'default-prefix="~/Games/prefixes"\n'


def test_cli_render_accepts_missing_live_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    repo_path = tmp_path / "config.ini"
    repo_path.write_text('default-prefix="~/Games/prefixes"\n', encoding="utf-8")

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

    assert completed.stdout == 'default-prefix="/home/tester/Games/prefixes"\n'

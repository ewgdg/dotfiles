from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages/linux/faugus-launcher/scripts/sync_faugus_config.py"
)
_MODULE_SPEC = importlib.util.spec_from_file_location("faugus_sync_module", _MODULE_PATH)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise RuntimeError(f"failed to load Faugus sync module from {_MODULE_PATH}")
module = importlib.util.module_from_spec(_MODULE_SPEC)
sys.modules[_MODULE_SPEC.name] = module
_MODULE_SPEC.loader.exec_module(module)


def test_capture_collapses_default_prefix_to_home_relative_path(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")

    captured = module.capture_config_text(
        'close-onlaunch=False\n'
        'default-prefix="/home/tester/Games/prefixes"\n'
        'playtime=42\n'
        'donate-last=2026-05\n'
        'system-tray=True\n'
    )

    assert 'default-prefix="~/Games/prefixes"' in captured
    assert "playtime=" not in captured
    assert "donate-last=" not in captured
    assert "system-tray=True" in captured


def test_render_expands_default_prefix_and_preserves_live_state(monkeypatch) -> None:
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
    )

    assert 'default-prefix="/home/tester/Games/prefixes"' in rendered
    assert "system-tray=True" in rendered
    assert "playtime=42" in rendered
    assert "future-key=keep-me" in rendered


def test_render_without_live_file_outputs_repo_keys_with_expanded_prefix(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")

    rendered = module.render_config_text(
        'default-prefix="~/Games/prefixes"\n'
        'system-tray=True\n',
    )

    assert rendered == 'default-prefix="/home/tester/Games/prefixes"\nsystem-tray=True\n'


def test_config_must_include_default_prefix() -> None:
    with pytest.raises(ValueError, match="default-prefix"):
        module.render_config_text("system-tray=True\n")


def test_cli_render_accepts_missing_live_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    repo_path = tmp_path / "config.ini"
    repo_path.write_text('default-prefix="~/Games/prefixes"\n', encoding="utf-8")

    completed = subprocess.run(
        [str(_MODULE_PATH), "render", str(repo_path), "--live-path", str(tmp_path / "missing")],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout == 'default-prefix="/home/tester/Games/prefixes"\n'

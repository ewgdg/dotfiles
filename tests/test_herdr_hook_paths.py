from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TEXT_REWRITE = REPO_ROOT / "scripts/text_rewrite.py"


@pytest.mark.parametrize(
    ("manifest_path", "target_name"),
    [
        ("packages/codex/package.toml", "f_codex_hooks_json"),
        ("packages/claude/package.toml", "f_claude_settings_json"),
    ],
)
def test_herdr_hook_targets_normalize_home_during_capture_and_render(
    manifest_path: str,
    target_name: str,
) -> None:
    with (REPO_ROOT / manifest_path).open("rb") as manifest_file:
        target = tomllib.load(manifest_file)["targets"][target_name]

    assert "scripts/text_rewrite.py" in target["capture"]
    assert "home collapse" in target["capture"]
    assert "scripts/text_rewrite.py" in target["render"]
    assert "home expand" in target["render"]


@pytest.mark.parametrize(
    ("config_path", "expected_hook_path"),
    [
        ("packages/codex/files/codex/hooks.json", "~/.codex/herdr-agent-state.sh"),
        ("packages/claude/files/claude/settings.json", "~/.claude/hooks/herdr-agent-state.sh"),
    ],
)
def test_herdr_hook_paths_are_home_relative_in_repo(
    config_path: str,
    expected_hook_path: str,
) -> None:
    config = json.loads((REPO_ROOT / config_path).read_text(encoding="utf-8"))
    hook_command = config["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    assert f"'{expected_hook_path}'" in hook_command


def test_claude_home_rewrites_explicitly_read_from_stdin() -> None:
    with (REPO_ROOT / "packages/claude/package.toml").open("rb") as manifest_file:
        target = tomllib.load(manifest_file)["targets"]["f_claude_settings_json"]

    assert target["capture"].endswith("home collapse -")
    assert target["render"].endswith("home expand -")


@pytest.mark.parametrize(
    ("config_path", "expected_hook_path"),
    [
        ("packages/codex/files/codex/hooks.json", "/home/tester/.codex/herdr-agent-state.sh"),
        (
            "packages/claude/files/claude/settings.json",
            "/home/tester/.claude/hooks/herdr-agent-state.sh",
        ),
    ],
)
def test_rendered_herdr_hook_path_has_no_json_escape_before_absolute_path(
    config_path: str,
    expected_hook_path: str,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(TEXT_REWRITE),
            "home",
            "expand",
            str(REPO_ROOT / config_path),
            "--home",
            "/home/tester",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert f"bash '{expected_hook_path}' session" in completed.stdout
    assert f'\\"{expected_hook_path}' not in completed.stdout

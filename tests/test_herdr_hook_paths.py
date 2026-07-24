from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import tomllib

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_target(manifest_path: str, target_name: str) -> dict[str, str]:
    with (REPO_ROOT / manifest_path).open("rb") as manifest_file:
        return tomllib.load(manifest_file)["targets"][target_name]


def hook_command(config: dict) -> str:
    return config["hooks"]["SessionStart"][0]["hooks"][0]["command"]


def config_with_hook(hook_path: str, **settings: str) -> dict:
    return {
        **settings,
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"bash '{hook_path}' session",
                        }
                    ]
                }
            ]
        },
    }


def test_claude_pipeline_uses_public_home_rewrite_after_json_selection() -> None:
    target = load_target("packages/claude/package.toml", "f_claude_settings_json")

    assert target["render"] == (
        "{{ JSON_RENDER }} --selector-type retain --selectors "
        "{{ vars.claude.settings_selectors|shell_args }} | "
        "dotman rewrite home expand -"
    )
    assert target["capture"] == (
        "{{ JSON_CAPTURE }} --selector-type remove --selectors "
        "{{ vars.claude.settings_selectors|shell_args }} | "
        "dotman rewrite home collapse -"
    )


def test_codex_pipeline_uses_public_home_rewrite_with_file_input() -> None:
    target = load_target("packages/codex/package.toml", "f_codex_hooks_json")

    assert target["render"] == 'dotman rewrite home expand "$DOTMAN_REPO_PATH"'
    assert target["capture"] == 'dotman rewrite home collapse "$DOTMAN_LIVE_PATH"'


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

    assert f"'{expected_hook_path}'" in hook_command(config)


def render_claude_target_command(
    template: str,
    *,
    command_name: str,
    live_path: Path,
    repo_path: Path,
) -> str:
    mode = "merge" if command_name == "render" else "cleanup"
    compare_path = live_path if command_name == "render" else repo_path
    transform_command = (
        f"dotman transform json {shlex.quote(str(live_path))} --stdout "
        f"--mode {mode} --compare-file {shlex.quote(str(compare_path))}"
    )
    if command_name == "render":
        transform_command += f" --overlay-file {shlex.quote(str(repo_path))}"

    return (
        template.replace(f"{{{{ JSON_{command_name.upper()} }}}}", transform_command)
        .replace(
            "{{ vars.claude.settings_selectors|shell_args }}",
            shlex.join(("model", "effortLevel")),
        )
    )


@pytest.mark.parametrize("command_name", ["render", "capture"])
def test_claude_pipeline_preserves_json_selection_and_normalizes_home(
    command_name: str,
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "repo.json"
    live_path = tmp_path / "live.json"
    repo_path.write_text(
        json.dumps(config_with_hook("~/.claude/hooks/herdr-agent-state.sh")),
        encoding="utf-8",
    )
    live_path.write_text(
        json.dumps(
            config_with_hook(
                "/home/tester/.claude/hooks/herdr-agent-state.sh",
                model="live-model",
                effortLevel="live-effort",
            )
        ),
        encoding="utf-8",
    )

    target = load_target("packages/claude/package.toml", "f_claude_settings_json")
    command = render_claude_target_command(
        target[command_name],
        command_name=command_name,
        live_path=live_path,
        repo_path=repo_path,
    )
    completed = subprocess.run(
        ["sh", "-c", command],
        env={**os.environ, "HOME": "/home/tester"},
        capture_output=True,
        text=True,
        check=True,
    )
    transformed = json.loads(completed.stdout)

    if command_name == "render":
        assert transformed["model"] == "live-model"
        assert transformed["effortLevel"] == "live-effort"
        assert "'/home/tester/.claude/hooks/herdr-agent-state.sh'" in hook_command(transformed)
    else:
        assert "model" not in transformed
        assert "effortLevel" not in transformed
        assert "'~/.claude/hooks/herdr-agent-state.sh'" in hook_command(transformed)


@pytest.mark.parametrize(
    ("command_name", "input_variable", "input_path", "expected_hook_path"),
    [
        (
            "render",
            "DOTMAN_REPO_PATH",
            "packages/codex/files/codex/hooks.json",
            "/home/tester/.codex/herdr-agent-state.sh",
        ),
        (
            "capture",
            "DOTMAN_LIVE_PATH",
            None,
            "~/.codex/herdr-agent-state.sh",
        ),
    ],
)
def test_codex_pipeline_preserves_file_behavior(
    command_name: str,
    input_variable: str,
    input_path: str | None,
    expected_hook_path: str,
    tmp_path: Path,
) -> None:
    if input_path is None:
        path = tmp_path / "hooks.json"
        path.write_text(
            json.dumps(config_with_hook("/home/tester/.codex/herdr-agent-state.sh")),
            encoding="utf-8",
        )
    else:
        path = REPO_ROOT / input_path

    target = load_target("packages/codex/package.toml", "f_codex_hooks_json")
    completed = subprocess.run(
        ["sh", "-c", target[command_name]],
        env={**os.environ, "HOME": "/home/tester", input_variable: str(path)},
        capture_output=True,
        text=True,
        check=True,
    )
    transformed = json.loads(completed.stdout)

    assert f"'{expected_hook_path}'" in hook_command(transformed)
    if command_name == "render":
        assert f'\\"{expected_hook_path}' not in completed.stdout

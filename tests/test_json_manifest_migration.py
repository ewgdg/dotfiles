from __future__ import annotations

import json
import os
import shlex
import subprocess
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DOTMAN_ROOT = Path(
    os.environ.get("DOTMAN_CANDIDATE_ROOT", REPO_ROOT.parent / "dotman")
)


def load_toml(relative_path: str) -> dict:
    with (REPO_ROOT / relative_path).open("rb") as file:
        return tomllib.load(file)


def render_with_candidate(template: str, context: dict) -> str:
    script = """
import json
import sys
from pathlib import Path
from dotman.templates import render_template_string

payload = json.load(sys.stdin)
print(render_template_string(payload["template"], payload["context"], base_dir=Path.cwd()))
"""
    completed = subprocess.run(
        ["uv", "run", "--project", str(CANDIDATE_DOTMAN_ROOT), "python", "-c", script],
        input=json.dumps({"template": template, "context": context}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.rstrip("\n")


def test_shared_json_aliases_use_public_dotman_cli() -> None:
    variables = load_toml("profiles/runtime/core.toml")["vars"]

    assert variables["JSON_TRANSFORM"] == "dotman transform json"


@pytest.mark.skipif(not (CANDIDATE_DOTMAN_ROOT / "pyproject.toml").is_file(), reason="candidate dotman checkout unavailable")
@pytest.mark.parametrize(
    ("manifest_path", "variable_group", "selector_variable", "target_path", "command_name", "selector_type"),
    [
        ("packages/arch-system/package.toml", "arch_system", "yay_config_selectors", "targets.f_config_yay_config_json", "render", "retain"),
        ("packages/arch-system/package.toml", "arch_system", "yay_config_selectors", "targets.f_config_yay_config_json", "capture", "remove"),
        ("packages/pi-coding-agent/package.toml", "pi_coding_agent", "settings_selectors", "targets.d_pi_agent.path_rules.0", "render", "retain"),
        ("packages/pi-coding-agent/package.toml", "pi_coding_agent", "settings_selectors", "targets.d_pi_agent.path_rules.0", "capture", "remove"),
    ],
)
def test_json_commands_preserve_selector_argv_and_transform_behavior(
    tmp_path: Path,
    manifest_path: str,
    variable_group: str,
    selector_variable: str,
    target_path: str,
    command_name: str,
    selector_type: str,
) -> None:
    core_variables = load_toml("profiles/runtime/core.toml")["vars"]
    manifest = load_toml(manifest_path)
    selectors = manifest["vars"][variable_group][selector_variable]
    target: object = manifest
    for component in target_path.split("."):
        target = target[int(component)] if component.isdigit() else target[component]  # type: ignore[index]
    template = target[command_name]  # type: ignore[index]

    live_path = tmp_path / "live.json"
    repo_path = tmp_path / "repo.json"
    all_keys = selectors + ["repoManaged"]
    live_path.write_text(json.dumps({key: f"live-{index}" for index, key in enumerate(all_keys)}), encoding="utf-8")
    repo_path.write_text(json.dumps({"repoManaged": f"repo-{len(selectors)}"}), encoding="utf-8")
    path_context = {
        "DOTMAN_LIVE_PATH": str(live_path),
        "DOTMAN_REPO_PATH": str(repo_path),
    }
    transform_command = core_variables["JSON_TRANSFORM"]
    command_aliases = {
        alias: render_with_candidate(
            core_variables[alias],
            {**path_context, "JSON_TRANSFORM": transform_command},
        )
        for alias in ("JSON_RENDER", "JSON_CAPTURE")
    }
    context = {
        **command_aliases,
        "vars": {variable_group: manifest["vars"][variable_group]},
    }
    rendered = render_with_candidate(template, context)
    argv = shlex.split(rendered)

    selector_start = argv.index("--selectors") + 1
    assert argv[selector_start:] == selectors
    assert argv[argv.index("--selector-type") + 1] == selector_type

    candidate_command = rendered.replace(
        "dotman transform json",
        f"uv run --project {shlex.quote(str(CANDIDATE_DOTMAN_ROOT))} dotman transform json",
        1,
    )
    completed = subprocess.run(
        ["sh", "-c", candidate_command],
        env={
            **os.environ,
            "DOTMAN_LIVE_PATH": str(live_path),
            "DOTMAN_REPO_PATH": str(repo_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    transformed = json.loads(completed.stdout)
    if command_name == "render":
        assert all(transformed[key] == f"live-{index}" for index, key in enumerate(selectors))
        assert transformed["repoManaged"] == f"repo-{len(selectors)}"
    else:
        assert set(transformed) == {"repoManaged"}

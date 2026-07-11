from __future__ import annotations

import json
import os
import shlex
import subprocess
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DOTMAN_ROOT = Path(os.environ.get("DOTMAN_CANDIDATE_ROOT", REPO_ROOT.parent / "dotman"))


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


def test_shared_toml_alias_uses_public_dotman_cli() -> None:
    variables = load_toml("profiles/runtime/core.toml")["vars"]
    assert variables["TOML_TRANSFORM"] == "dotman transform toml"


@pytest.mark.skipif(not (CANDIDATE_DOTMAN_ROOT / "pyproject.toml").is_file(), reason="candidate dotman checkout unavailable")
@pytest.mark.parametrize(
    ("manifest_path", "group", "selector_name", "target_path", "command_name", "selector_type"),
    [
        ("packages/codex/package.toml", "codex", "config_selectors", "targets.f_codex_config_toml", "render", "retain"),
        ("packages/codex/package.toml", "codex", "config_selectors", "targets.f_codex_config_toml", "capture", "remove"),
        ("packages/noctalia/package.toml", "noctalia", "config_selectors", "targets.d_config_noctalia.path_rules.0", "capture", "remove"),
    ],
)
def test_toml_commands_render_native_selector_argv(
    manifest_path: str, group: str, selector_name: str, target_path: str, command_name: str, selector_type: str
) -> None:
    core = load_toml("profiles/runtime/core.toml")["vars"]
    manifest = load_toml(manifest_path)
    target: object = manifest
    for component in target_path.split("."):
        target = target[int(component)] if component.isdigit() else target[component]  # type: ignore[index]
    alias_name = f"TOML_{command_name.upper()}"
    context = {"DOTMAN_LIVE_PATH": "/tmp/live.toml", "DOTMAN_REPO_PATH": "/tmp/repo.toml", "TOML_TRANSFORM": core["TOML_TRANSFORM"]}
    alias = render_with_candidate(core[alias_name], context)
    rendered = render_with_candidate(target[command_name], {alias_name: alias, "TOML_TRANSFORM": core["TOML_TRANSFORM"], "DOTMAN_REPO_PATH": "/tmp/repo.toml", "vars": {group: manifest["vars"][group]}})  # type: ignore[index]
    argv = shlex.split(rendered)
    selectors = manifest["vars"][group][selector_name]
    assert argv[argv.index("--selectors") + 1 :] == selectors
    assert argv[argv.index("--selector-type") + 1] == selector_type
    if group == "noctalia":
        assert argv[:5] == ["noctalia", "config", "export", "|", "dotman"]
        assert argv[7] == "-"


@pytest.mark.skipif(not (CANDIDATE_DOTMAN_ROOT / "pyproject.toml").is_file(), reason="candidate dotman checkout unavailable")
def test_noctalia_capture_reads_stdin_and_preserves_unselected_toml(tmp_path: Path) -> None:
    core = load_toml("profiles/runtime/core.toml")["vars"]
    manifest = load_toml("packages/noctalia/package.toml")
    template = manifest["targets"]["d_config_noctalia"]["path_rules"][0]["capture"]
    repo_path = tmp_path / "repo.toml"
    repo_path.write_text('theme = "repo"\n', encoding="utf-8")
    rendered = render_with_candidate(
        template,
        {
            "TOML_TRANSFORM": core["TOML_TRANSFORM"],
            "DOTMAN_REPO_PATH": str(repo_path),
            "vars": {"noctalia": manifest["vars"]["noctalia"]},
        },
    )
    candidate = rendered.replace(
        "noctalia config export",
        "printf 'lockscreen_widgets = [1]\\ntheme = \"live\"\\n'",
        1,
    ).replace(
        "dotman transform toml",
        f"uv run --project {shlex.quote(str(CANDIDATE_DOTMAN_ROOT))} dotman transform toml",
        1,
    )
    completed = subprocess.run(
        ["sh", "-c", candidate],
        env={**os.environ, "DOTMAN_REPO_PATH": str(repo_path)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert tomllib.loads(completed.stdout) == {"theme": "live"}

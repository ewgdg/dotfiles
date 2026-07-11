from __future__ import annotations

import json
import os
import plistlib
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


def test_shared_plist_aliases_use_public_dotman_cli() -> None:
    variables = load_toml("profiles/runtime/core.toml")["vars"]

    assert variables["PLIST_TRANSFORM"] == "dotman transform plist"
    assert "$DOTMAN_REPO_ROOT/scripts/plist_transform.py" not in variables["PLIST_RENDER"]
    assert "$DOTMAN_REPO_ROOT/scripts/plist_transform.py" not in variables["PLIST_CAPTURE"]


@pytest.mark.skipif(
    not (CANDIDATE_DOTMAN_ROOT / "pyproject.toml").is_file(),
    reason="candidate dotman checkout unavailable",
)
@pytest.mark.parametrize(
    ("manifest_path", "variable_group", "selector_variable", "target_name", "command_name", "selector_type"),
    [
        ("packages/macos-preferences/package.toml", "macos_preferences", "global_selectors", "f_library_preferences_globalpreferences_plist", "render", "remove"),
        ("packages/macos-preferences/package.toml", "macos_preferences", "global_selectors", "f_library_preferences_globalpreferences_plist", "capture", "retain"),
        ("packages/mac/linearmouse/package.toml", "linearmouse", "config_selectors", "f_library_preferences_com_lujjjh_linearmouse_plist", "render", "retain"),
        ("packages/mac/linearmouse/package.toml", "linearmouse", "config_selectors", "f_library_preferences_com_lujjjh_linearmouse_plist", "capture", "remove"),
    ],
)
def test_plist_selector_commands_preserve_argv_and_behavior(
    tmp_path: Path,
    manifest_path: str,
    variable_group: str,
    selector_variable: str,
    target_name: str,
    command_name: str,
    selector_type: str,
) -> None:
    core_variables = load_toml("profiles/runtime/core.toml")["vars"]
    manifest = load_toml(manifest_path)
    selectors = manifest["vars"][variable_group][selector_variable]
    template = manifest["targets"][target_name][command_name]
    live_path = tmp_path / "live.plist"
    repo_path = tmp_path / "repo.plist"
    selected_key = selectors[0]
    plistlib.dump({selected_key: "live-selected", "repoManaged": "live-old", "localOnly": "live-local"}, live_path.open("wb"))
    plistlib.dump({"repoManaged": "repo-new"}, repo_path.open("wb"))
    path_context = {"DOTMAN_LIVE_PATH": str(live_path), "DOTMAN_REPO_PATH": str(repo_path)}
    command_aliases = {
        alias: render_with_candidate(
            core_variables[alias],
            {**path_context, "PLIST_TRANSFORM": core_variables["PLIST_TRANSFORM"]},
        )
        for alias in ("PLIST_RENDER", "PLIST_CAPTURE")
    }
    rendered = render_with_candidate(
        template,
        {**command_aliases, "vars": {variable_group: manifest["vars"][variable_group]}},
    )
    argv = shlex.split(rendered)

    assert argv[argv.index("--selectors") + 1 :] == selectors
    assert argv[argv.index("--selector-type") + 1] == selector_type
    assert argv[argv.index("--output-format") + 1] == ("binary" if command_name == "render" else "xml")

    candidate_command = rendered.replace(
        "dotman transform plist",
        f"uv run --project {shlex.quote(str(CANDIDATE_DOTMAN_ROOT))} dotman transform plist",
        1,
    )
    completed = subprocess.run(
        ["sh", "-c", candidate_command],
        env={
            **os.environ,
            "DOTMAN_LIVE_PATH": str(live_path),
            "DOTMAN_REPO_PATH": str(repo_path),
        },
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    transformed = plistlib.loads(completed.stdout)
    if selector_type == "retain":
        expected = (
            {selected_key: "live-selected"}
            if command_name == "capture"
            else {selected_key: "live-selected", "repoManaged": "repo-new"}
        )
    else:
        expected = (
            {"localOnly": "live-local", "repoManaged": "repo-new"}
            if command_name == "render"
            else {"localOnly": "live-local", "repoManaged": "live-old"}
        )
    assert transformed == expected


@pytest.mark.skipif(
    not (CANDIDATE_DOTMAN_ROOT / "pyproject.toml").is_file(),
    reason="candidate dotman checkout unavailable",
)
def test_selectorless_macos_target_keeps_binary_render_and_xml_capture(tmp_path: Path) -> None:
    core_variables = load_toml("profiles/runtime/core.toml")["vars"]
    manifest = load_toml("packages/macos-preferences/package.toml")
    target = manifest["targets"]["f_library_preferences_com_apple_symbolichotkeys_plist"]
    for command_name, expected_format in (("render", "binary"), ("capture", "xml")):
        rendered_alias = render_with_candidate(
            core_variables[f"PLIST_{command_name.upper()}"],
            {
                "DOTMAN_LIVE_PATH": str(tmp_path / "live.plist"),
                "DOTMAN_REPO_PATH": str(tmp_path / "repo.plist"),
                "PLIST_TRANSFORM": core_variables["PLIST_TRANSFORM"],
            },
        )
        rendered = render_with_candidate(target[command_name], {f"PLIST_{command_name.upper()}": rendered_alias})
        argv = shlex.split(rendered)
        assert "--selectors" not in argv
        assert argv[argv.index("--output-format") + 1] == expected_format

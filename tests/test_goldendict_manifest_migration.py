from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import tomllib

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


@pytest.mark.skipif(
    not (CANDIDATE_DOTMAN_ROOT / "pyproject.toml").is_file(),
    reason="candidate dotman checkout unavailable",
)
@pytest.mark.parametrize("action", ["render", "capture"])
def test_goldendict_manifest_renders_native_selector_arrays_as_literal_argv(action: str) -> None:
    core_variables = load_toml("profiles/runtime/core.toml")["vars"]
    manifest = load_toml("packages/goldendict/package.toml")
    target = manifest["targets"]["f_config_goldendict_config"]
    config_selectors = ["config/two words", "config/single'quote", "re:^x;$(touch nope)*[z]"]
    unordered_selectors = ["config/list with spaces", "config/$HOME;literal"]
    variables = {**manifest["vars"]["goldendict"], "config_selectors": config_selectors, "unordered_child_selectors": unordered_selectors}

    rendered = render_with_candidate(
        target[action],
        {
            "UV_RUN": "uv run --project /repo with spaces",
            "DOTMAN_PACKAGE_ROOT": "/package root;literal",
            "DOTMAN_LIVE_PATH": "/live path/config.xml",
            "DOTMAN_REPO_PATH": "/repo path/config.xml",
            "vars": {"goldendict": variables},
        },
    )
    argv = shlex.split(rendered)

    assert core_variables["XML_TRANSFORM"] == "dotman transform xml"
    helper_index = argv.index("$DOTMAN_PACKAGE_ROOT/scripts/sync_goldendict_config.py")
    assert argv[helper_index + 1] == action
    assert argv[helper_index + 2] == "$DOTMAN_LIVE_PATH"
    next_index = helper_index + 3
    if action == "render":
        assert argv[next_index] == "$DOTMAN_REPO_PATH"
        next_index += 1
    assert argv[next_index : next_index + 2] == ["--sort-children", unordered_selectors[0]]
    assert argv[next_index + 2] == unordered_selectors[1]
    selectors_index = argv.index("--selectors")
    assert selectors_index == next_index + 3
    assert argv[selectors_index + 1 :] == config_selectors
    assert isinstance(manifest["vars"]["goldendict"]["config_selectors"], list)
    assert isinstance(manifest["vars"]["goldendict"]["unordered_child_selectors"], list)


def candidate_path(tmp_path: Path) -> Path:
    bin_path = tmp_path / "candidate-bin"
    bin_path.mkdir()
    executable = bin_path / "dotman"
    executable.write_text(
        f"#!/bin/sh\nexec uv run --project {shlex.quote(str(CANDIDATE_DOTMAN_ROOT))} dotman \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return bin_path


@pytest.mark.skipif(
    not (CANDIDATE_DOTMAN_ROOT / "pyproject.toml").is_file(),
    reason="candidate dotman checkout unavailable",
)
def test_goldendict_helper_runs_capture_and_render_outside_checkout_and_propagates_failure(tmp_path: Path) -> None:
    outside_path = tmp_path / "outside checkout"
    outside_path.mkdir()
    live_path = tmp_path / "live config.xml"
    repo_path = tmp_path / "repo config.xml"
    live_path.write_text("<config><paths><path>/live/dicts</path></paths><keep/><WindowGeometry x=\"1\"/></config>", encoding="utf-8")
    repo_path.write_text("<config><paths><path>${XDG_DOCUMENTS_DIR:-$HOME/Documents}/Dictionaries</path></paths><keep/></config>", encoding="utf-8")
    command = ["uv", "run", "--project", str(REPO_ROOT), str(REPO_ROOT / "packages/goldendict/scripts/sync_goldendict_config.py")]
    environment = {**os.environ, "PATH": f"{candidate_path(tmp_path)}:{os.environ['PATH']}", "HOME": "/home/tester", "XDG_DOCUMENTS_DIR": "/docs with spaces"}

    capture = subprocess.run(command + ["capture", str(live_path), "--selectors", "config/WindowGeometry"], cwd=outside_path, env=environment, text=True, capture_output=True)
    assert capture.returncode == 0, capture.stderr
    assert "{{ vars.goldendict.dictionary_dir }}" in capture.stdout
    assert "WindowGeometry" not in capture.stdout

    render = subprocess.run(command + ["render", str(live_path), str(repo_path), "--selectors", "config/WindowGeometry"], cwd=outside_path, env=environment, text=True, capture_output=True)
    assert render.returncode == 0, render.stderr
    assert "/docs with spaces/Dictionaries" in render.stdout
    assert "WindowGeometry" in render.stdout

    live_path.write_text("<config><broken></config>", encoding="utf-8")
    failure = subprocess.run(command + ["capture", str(live_path), "--selectors", "config/x"], cwd=outside_path, env=environment, text=True, capture_output=True)
    assert failure.returncode != 0
    assert failure.stderr
    assert "mismatched tag" in failure.stderr.lower()

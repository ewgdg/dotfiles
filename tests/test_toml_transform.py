from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "toml_transform.py"


def load_module():
    spec = importlib.util.spec_from_file_location("toml_transform", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def test_toml_engine_declares_typed_selectors() -> None:
    selector_specs = {spec.name: spec for spec in MODULE.TomlTransformEngine.selector_specs()}

    assert selector_specs["key"].option_name(MODULE.SelectorAction.RETAIN) == "--retain-key"
    assert (
        selector_specs["table_regex"].option_name(MODULE.SelectorAction.RETAIN)
        == "--retain-table-regex"
    )


def test_main_accepts_typed_selector_flags(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.toml"
    live_path = tmp_path / "live.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text(
        """approval_policy = "on-request"

[mcp_servers.context7]
command = "npx"
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """approval_policy = "on-request"
model = "gpt-5.4"

[mcp_servers.playwright.env]
PLAYWRIGHT_MCP_EXTENSION_TOKEN = "secret"
""",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(repo_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(live_path),
            "--retain-key",
            "model",
            "--retain-table-regex",
            "^mcp_servers\\.playwright\\.env$",
        ]
    )

    assert exit_code == 0
    merged_doc = MODULE.load_document(output_path)
    assert merged_doc["model"] == "gpt-5.4"
    assert (
        merged_doc["mcp_servers"]["playwright"]["env"]["PLAYWRIGHT_MCP_EXTENSION_TOKEN"]
        == "secret"
    )


def test_parse_key_paths_and_table_regexes() -> None:
    key_paths = MODULE.parse_key_paths(["model", "model_reasoning_effort"])
    table_regexes = MODULE.compile_table_regexes(
        ["^projects\\.", "^mcp_servers\\.playwright\\.env$"]
    )

    assert key_paths == [("model",), ("model_reasoning_effort",)]
    assert [pattern.pattern for pattern in table_regexes] == [
        "^projects\\.",
        "^mcp_servers\\.playwright\\.env$",
    ]


def test_retain_matchers_in_strip_mode_keeps_only_selected_content(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text(
        """approval_policy = "on-request"
model = "gpt-5.4"

[mcp_servers.context7]
command = "npx"

[projects."/tmp/example"]
trust_level = "trusted"
""",
        encoding="utf-8",
    )

    retained_doc = MODULE.build_document_with_retained_matchers(
        MODULE.load_document(repo_path),
        {("model",)},
        [MODULE.re.compile(r"^projects\.")],
    )
    MODULE.write_document_if_changed(output_path, retained_doc, mode_reference_path=repo_path)

    output = output_path.read_text(encoding="utf-8")
    assert 'model = "gpt-5.4"' in output
    assert "[projects" in output
    assert "approval_policy" not in output
    assert "mcp_servers" not in output


def test_write_document_with_compare_file_skips_rewrite_for_matching_output(
    tmp_path: Path,
 ) -> None:
    repo_path = tmp_path / "repo.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text('model = "gpt-5.4"\n', encoding="utf-8")
    retained_doc = MODULE.load_document(repo_path)
    output_path.write_text(retained_doc.as_string(), encoding="utf-8")
    os.utime(output_path, ns=(1, 1))

    MODULE.write_document_if_changed(
        output_path,
        retained_doc,
        mode_reference_path=repo_path,
        compare_path=output_path,
    )

    assert output_path.stat().st_mtime_ns == 1


def test_write_document_without_compare_file_rewrites_matching_output(
    tmp_path: Path,
 ) -> None:
    repo_path = tmp_path / "repo.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text('model = "gpt-5.4"\n', encoding="utf-8")
    retained_doc = MODULE.load_document(repo_path)
    output_path.write_text(retained_doc.as_string(), encoding="utf-8")
    os.utime(output_path, ns=(1, 1))

    MODULE.write_document_if_changed(
        output_path,
        retained_doc,
        mode_reference_path=repo_path,
    )

    assert output_path.stat().st_mtime_ns != 1


def test_merge_replaces_unmanaged_live_keys_but_preserves_selected_keys(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.toml"
    live_path = tmp_path / "live.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text(
        """approval_policy = "on-request"
web_search = "live"

[mcp_servers.context7]
command = "npx"
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """approval_policy = "on-request"
model = "gpt-5.4"

[mcp_servers.context7]
command = "npx"

[mcp_servers.playwright]
command = "npx"

[mcp_servers.playwright.env]
PLAYWRIGHT_MCP_EXTENSION_TOKEN = "secret"

[projects."/tmp/example"]
trust_level = "trusted"
""",
        encoding="utf-8",
    )

    MODULE.merge_keys(
        repo_path,
        output_path,
        live_path,
        {
            ("model",),
            ("mcp_servers", "playwright", "env", "PLAYWRIGHT_MCP_EXTENSION_TOKEN"),
        },
        [],
    )

    merged_doc = MODULE.load_document(output_path)

    assert merged_doc["model"] == "gpt-5.4"
    assert "projects" not in merged_doc
    assert "playwright" in merged_doc["mcp_servers"]
    assert "command" not in merged_doc["mcp_servers"]["playwright"]
    assert (
        merged_doc["mcp_servers"]["playwright"]["env"]["PLAYWRIGHT_MCP_EXTENSION_TOKEN"]
        == "secret"
    )


def test_merge_restores_regex_selected_tables(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.toml"
    live_path = tmp_path / "live.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text(
        """approval_policy = "on-request"

[mcp_servers.context7]
command = "npx"
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """approval_policy = "on-request"

[mcp_servers.context7]
command = "npx"

[mcp_servers.playwright]
command = "npx"

[mcp_servers.playwright.env]
PLAYWRIGHT_MCP_EXTENSION_TOKEN = "secret"
""",
        encoding="utf-8",
    )

    MODULE.merge_keys(
        repo_path,
        output_path,
        live_path,
        set(),
        [MODULE.re.compile(r"^mcp_servers\.playwright\.env$")],
    )

    merged_doc = MODULE.load_document(output_path)

    assert "context7" in merged_doc["mcp_servers"]
    assert "playwright" in merged_doc["mcp_servers"]
    assert "command" not in merged_doc["mcp_servers"]["playwright"]
    assert (
        merged_doc["mcp_servers"]["playwright"]["env"]["PLAYWRIGHT_MCP_EXTENSION_TOKEN"]
        == "secret"
    )


def test_merge_skips_missing_preserved_paths(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.toml"
    live_path = tmp_path / "live.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text(
        """approval_policy = "on-request"
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """approval_policy = "on-request"
""",
        encoding="utf-8",
    )

    MODULE.merge_keys(
        repo_path,
        output_path,
        live_path,
        {("mcp_servers", "playwright", "env", "PLAYWRIGHT_MCP_EXTENSION_TOKEN")},
        [],
    )

    merged_doc = MODULE.load_document(output_path)

    assert "mcp_servers" not in merged_doc


def test_merge_strip_matchers_merges_everything_else_from_overlay(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.toml"
    live_path = tmp_path / "live.toml"
    output_path = tmp_path / "output.toml"

    repo_path.write_text(
        """approval_policy = "on-request"
model = "repo-model"

[mcp_servers.context7]
command = "repo-context7"

[projects."/tmp/example"]
trust_level = "repo"
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """approval_policy = "live"
model = "live-model"

[mcp_servers.context7]
command = "live-context7"

[mcp_servers.playwright]
command = "live-playwright"

[projects."/tmp/example"]
trust_level = "trusted"
""",
        encoding="utf-8",
    )

    MODULE.merge_keys_except_stripped(
        repo_path,
        output_path,
        live_path,
        [("model",)],
        [MODULE.re.compile(r"^projects\.")],
    )

    merged_doc = MODULE.load_document(output_path)

    assert merged_doc["approval_policy"] == "live"
    assert merged_doc["model"] == "repo-model"
    assert merged_doc["mcp_servers"]["context7"]["command"] == "live-context7"
    assert merged_doc["mcp_servers"]["playwright"]["command"] == "live-playwright"
    assert merged_doc["projects"]["/tmp/example"]["trust_level"] == "repo"


def test_merge_preserves_overlay_key_order_across_hash_seeds(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.toml"
    live_path = tmp_path / "live.toml"

    repo_path.write_text(
        'approval_policy = "on-request"\n',
        encoding="utf-8",
    )
    live_path.write_text(
        """approval_policy = "on-request"
model_reasoning_effort = "high"
model = "gpt-5.4"
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1])
repo_path = Path(sys.argv[2])
live_path = Path(sys.argv[3])
output_path = Path(sys.argv[4])

spec = importlib.util.spec_from_file_location("toml_transform_subprocess", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"failed to load module from {script_path}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

module.merge_keys(
    repo_path,
    output_path,
    live_path,
    {("model",), ("model_reasoning_effort",)},
    [],
)
print(output_path.read_text(encoding="utf-8"))
""",
            str(SCRIPT_PATH),
            str(repo_path),
            str(live_path),
            str(tmp_path / "output.toml"),
        ],
        capture_output=True,
        check=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": "1"},
    )

    output = completed.stdout
    assert output.index('model_reasoning_effort = "high"') < output.index('model = "gpt-5.4"')

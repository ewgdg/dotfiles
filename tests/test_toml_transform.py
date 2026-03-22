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


def test_parse_key_matchers_accepts_single_space_delimited_argument() -> None:
    key_paths, table_regexes = MODULE.parse_key_matchers(
        ["model model_reasoning_effort re:^projects\\. re:^mcp_servers\\.playwright\\.env$"]
    )

    assert key_paths == [("model",), ("model_reasoning_effort",)]
    assert [pattern.pattern for pattern in table_regexes] == [
        "^projects\\.",
        "^mcp_servers\\.playwright\\.env$",
    ]


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

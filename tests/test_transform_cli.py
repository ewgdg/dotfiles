from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "scripts" / "transform_cli.py"
ENGINE_PATH = REPO_ROOT / "scripts" / "transform_engine.py"


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI_MODULE = load_module("transform_cli", CLI_PATH)
ENGINE_MODULE = load_module("transform_engine_for_cli", ENGINE_PATH)


class RecordingEngine(ENGINE_MODULE.BaseTransformEngine):
    name = "recording"
    SELECTOR_SPECS = (
        ENGINE_MODULE.SelectorSpec(
            name="key",
            cli_flag="key",
            description="exact key selector",
        ),
        ENGINE_MODULE.SelectorSpec(
            name="table_regex",
            cli_flag="table-regex",
            description="regex table selector",
        ),
    )

    def __init__(self) -> None:
        self.requests: list[ENGINE_MODULE.TransformRequest] = []

    def configure_parser(self, parser) -> None:
        parser.add_argument("--sort-attributes", action="store_true")

    def build_engine_options(self, parsed_args) -> dict[str, bool]:
        return {"sort_attributes": parsed_args.sort_attributes}

    def transform(self, request: ENGINE_MODULE.TransformRequest) -> None:
        self.validate_request(request)
        self.requests.append(request)


def test_shared_cli_builds_request_with_typed_selector_flags(tmp_path: Path) -> None:
    engine = RecordingEngine()

    exit_code = CLI_MODULE.run_engine_cli(
        engine,
        [
            str(tmp_path / "base.toml"),
            str(tmp_path / "output.toml"),
            "--mode",
            "merge",
            "--overlay-file",
            str(tmp_path / "live.toml"),
            "--sort-attributes",
            "--retain-key",
            "model",
            "--retain-table-regex",
            "^projects\\.",
        ],
    )

    assert exit_code == 0
    assert len(engine.requests) == 1
    request = engine.requests[0]
    assert request.mode == ENGINE_MODULE.TransformMode.MERGE
    assert request.selector_action == ENGINE_MODULE.SelectorAction.RETAIN
    assert request.selector_values("key") == ("model",)
    assert request.selector_values("table_regex") == ("^projects\\.",)
    assert request.engine_option("sort_attributes") is True


def test_shared_cli_rejects_mixed_retain_and_strip_flags(tmp_path: Path) -> None:
    engine = RecordingEngine()

    with pytest.raises(SystemExit, match="2"):
        CLI_MODULE.run_engine_cli(
            engine,
            [
                str(tmp_path / "base.toml"),
                str(tmp_path / "output.toml"),
                "--mode",
                "strip",
                "--retain-key",
                "model",
                "--strip-table-regex",
                "^projects\\.",
            ],
        )


class SelectorOptionalEngine(ENGINE_MODULE.BaseTransformEngine):
    name = "selector-optional"
    SELECTOR_SPECS = (
        ENGINE_MODULE.SelectorSpec(
            name="key",
            cli_flag="key",
            description="exact key selector",
        ),
    )

    def requires_selectors(self) -> bool:
        return False

    def __init__(self) -> None:
        self.requests: list[ENGINE_MODULE.TransformRequest] = []

    def transform(self, request: ENGINE_MODULE.TransformRequest) -> None:
        self.validate_request(request)
        self.requests.append(request)


def test_shared_cli_allows_no_selector_flags_when_engine_supports_identity_mode(
    tmp_path: Path,
) -> None:
    engine = SelectorOptionalEngine()

    exit_code = CLI_MODULE.run_engine_cli(
        engine,
        [
            str(tmp_path / "base.plist"),
            str(tmp_path / "output.plist"),
            "--mode",
            "strip",
        ],
    )

    assert exit_code == 0
    assert len(engine.requests) == 1
    request = engine.requests[0]
    assert request.selector_action == ENGINE_MODULE.SelectorAction.RETAIN
    assert request.selector_values("key") == ()

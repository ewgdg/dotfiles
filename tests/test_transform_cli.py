from __future__ import annotations

from pathlib import Path

import pytest

from scripts import transform_cli as CLI_MODULE
from scripts import transform_engine as ENGINE_MODULE


class RecordingEngine(ENGINE_MODULE.BaseTransformEngine):
    name = "recording"
    SELECTOR_SPECS = (
        ENGINE_MODULE.SelectorSpec(
            name="key",
            prefix="exact",
            is_default=True,
            description="exact key selector",
        ),
        ENGINE_MODULE.SelectorSpec(
            name="table_regex",
            prefix="re",
            description="regex table selector",
        ),
    )

    def __init__(self) -> None:
        self.requests: list[ENGINE_MODULE.TransformRequest] = []

    def configure_parser(self, parser) -> None:
        parser.add_argument("--sort-attributes", action="store_true")

    def build_engine_options(self, parsed_args) -> dict[str, bool]:
        return {
            "sort_attributes": parsed_args.sort_attributes,
            "stdout": parsed_args.stdout,
        }

    def transform(self, request: ENGINE_MODULE.TransformRequest) -> ENGINE_MODULE.TransformOutput:
        self.validate_request(request)
        self.requests.append(request)
        return ENGINE_MODULE.TransformOutput(content="ok\n", mode_reference_path=request.base_path)


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
            "--selector-type",
            "retain",
            "--selectors",
            "model",
            "re:^projects\\.",
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





class SelectorOptionalEngine(ENGINE_MODULE.BaseTransformEngine):
    name = "selector-optional"
    SELECTOR_SPECS = (
        ENGINE_MODULE.SelectorSpec(
            name="key",
            prefix="exact",
            is_default=True,
            description="exact key selector",
        ),
    )

    def requires_selectors(self) -> bool:
        return False

    def __init__(self) -> None:
        self.requests: list[ENGINE_MODULE.TransformRequest] = []

    def transform(self, request: ENGINE_MODULE.TransformRequest) -> ENGINE_MODULE.TransformOutput:
        self.validate_request(request)
        self.requests.append(request)
        return ENGINE_MODULE.TransformOutput(content="ok\n", mode_reference_path=request.base_path)


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
            "cleanup",
        ],
    )

    assert exit_code == 0
    assert len(engine.requests) == 1
    request = engine.requests[0]
    assert request.selector_action == ENGINE_MODULE.SelectorAction.RETAIN
    assert request.selector_values("key") == ()


def test_shared_cli_accepts_stdout_without_output_path(tmp_path: Path) -> None:
    engine = RecordingEngine()

    exit_code = CLI_MODULE.run_engine_cli(
        engine,
        [
            str(tmp_path / "base.toml"),
            "--mode",
            "cleanup",
            "--stdout",
            "--selector-type",
            "retain",
            "--selectors",
            "model",
        ],
    )

    assert exit_code == 0
    request = engine.requests[0]
    assert request.output_path is None
    assert request.engine_option("stdout") is True


def test_shared_cli_help_text_describes_base_targeting() -> None:
    parser = CLI_MODULE.build_parser(RecordingEngine())
    help_by_dest = {
        action.dest: action.help
        for action in parser._actions
        if action.help is not None
    }

    assert help_by_dest["base_path"] == "Base file. Selectors always apply to this file."
    assert help_by_dest["output_path"] == "Transformed output path. Optional when --stdout is used."
    assert (
        help_by_dest["overlay_path"]
        == "Overlay file applied on top of the filtered base. Required when --mode=merge."
    )
    assert (
        help_by_dest["selector_type"]
        == "Preserve or remove the selected region from the base file."
    )
    assert (
        help_by_dest["selectors"]
        == "List of base-file matchers/selectors with optional prefixes."
    )
    assert help_by_dest["stdout"] == "Write the transformed output to stdout instead of a file."

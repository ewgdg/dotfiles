from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "transform_engine.py"


def load_module():
    spec = importlib.util.spec_from_file_location("transform_engine", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


class DummyEngine(MODULE.BaseTransformEngine):
    name = "dummy"
    SELECTOR_SPECS = (
        MODULE.SelectorSpec(
            name="key",
            cli_flag="key",
            description="Exact key selector",
        ),
    )

    def transform(self, request: MODULE.TransformRequest) -> None:
        self.validate_request(request)


def test_selector_spec_builds_typed_cli_flags() -> None:
    spec = MODULE.SelectorSpec(
        name="table_regex",
        cli_flag="table-regex",
        description="Regex table selector",
    )

    assert spec.option_name(MODULE.SelectorAction.RETAIN) == "--retain-table-regex"
    assert spec.option_name(MODULE.SelectorAction.STRIP) == "--strip-table-regex"


def test_transform_request_requires_overlay_in_merge_mode(tmp_path: Path) -> None:
    request = MODULE.TransformRequest(
        base_path=tmp_path / "base",
        output_path=tmp_path / "output",
        mode=MODULE.TransformMode.MERGE,
        selector_action=MODULE.SelectorAction.RETAIN,
        selectors_by_type={"key": ("model",)},
    )

    with pytest.raises(ValueError, match="overlay_path is required"):
        request.validate_basic()


def test_transform_request_rejects_overlay_in_strip_mode(tmp_path: Path) -> None:
    request = MODULE.TransformRequest(
        base_path=tmp_path / "base",
        output_path=tmp_path / "output",
        mode=MODULE.TransformMode.STRIP,
        selector_action=MODULE.SelectorAction.STRIP,
        selectors_by_type={"key": ("model",)},
        overlay_path=tmp_path / "live",
    )

    with pytest.raises(ValueError, match="only valid when mode=merge"):
        request.validate_basic()


def test_base_engine_rejects_unknown_selector_types(tmp_path: Path) -> None:
    engine = DummyEngine()
    request = MODULE.TransformRequest(
        base_path=tmp_path / "base",
        output_path=tmp_path / "output",
        mode=MODULE.TransformMode.STRIP,
        selector_action=MODULE.SelectorAction.RETAIN,
        selectors_by_type={"table_regex": (r"^projects\.",)},
    )

    with pytest.raises(ValueError, match="does not support selector types"):
        engine.validate_request(request)

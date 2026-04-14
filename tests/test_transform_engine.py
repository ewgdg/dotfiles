from __future__ import annotations

import io
from pathlib import Path

import pytest

from scripts import transform_engine as MODULE


class DummyEngine(MODULE.BaseTransformEngine):
    name = "dummy"
    SELECTOR_SPECS = (
        MODULE.SelectorSpec(
            name="key",
            prefix="exact",
            is_default=True,
            description="Exact key selector",
        ),
    )

    def transform(self, request: MODULE.TransformRequest) -> MODULE.TransformOutput:
        self.validate_request(request)
        return MODULE.TransformOutput(content="ok\n", mode_reference_path=request.base_path)


def test_selector_spec_records_prefix_and_default_status() -> None:
    spec = MODULE.SelectorSpec(
        name="table_regex",
        prefix="re",
        description="Regex table selector",
    )

    assert spec.prefix == "re"
    assert spec.is_default is False


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


def test_transform_request_rejects_overlay_in_cleanup_mode(tmp_path: Path) -> None:
    request = MODULE.TransformRequest(
        base_path=tmp_path / "base",
        output_path=tmp_path / "output",
        mode=MODULE.TransformMode.CLEANUP,
        selector_action=MODULE.SelectorAction.REMOVE,
        selectors_by_type={"key": ("model",)},
        overlay_path=tmp_path / "live",
    )

    with pytest.raises(ValueError, match="only valid when mode=merge"):
        request.validate_basic()


def test_transform_request_requires_output_path_without_stdout(tmp_path: Path) -> None:
    request = MODULE.TransformRequest(
        base_path=tmp_path / "base",
        output_path=None,
        mode=MODULE.TransformMode.CLEANUP,
        selector_action=MODULE.SelectorAction.RETAIN,
        selectors_by_type={"key": ("model",)},
    )

    with pytest.raises(ValueError, match="output_path is required unless stdout output is enabled"):
        request.validate_basic()


def test_transform_request_allows_stdout_without_output_path(tmp_path: Path) -> None:
    request = MODULE.TransformRequest(
        base_path=tmp_path / "base",
        output_path=None,
        mode=MODULE.TransformMode.CLEANUP,
        selector_action=MODULE.SelectorAction.RETAIN,
        selectors_by_type={"key": ("model",)},
        engine_options={"stdout": True},
    )

    request.validate_basic()


def test_base_engine_rejects_unknown_selector_types(tmp_path: Path) -> None:
    engine = DummyEngine()
    request = MODULE.TransformRequest(
        base_path=tmp_path / "base",
        output_path=tmp_path / "output",
        mode=MODULE.TransformMode.CLEANUP,
        selector_action=MODULE.SelectorAction.RETAIN,
        selectors_by_type={"table_regex": (r"^projects\.",)},
    )

    with pytest.raises(ValueError, match="does not support selector types"):
        engine.validate_request(request)


def test_emit_transform_output_decodes_binary_when_stdout_is_text_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_path = tmp_path / "base"
    base_path.write_text("ref\n", encoding="utf-8")

    fake_stdout = io.StringIO()
    monkeypatch.setattr(MODULE.sys, "stdout", fake_stdout)

    MODULE.emit_transform_output(
        None,
        MODULE.TransformOutput(content="snowman ☃".encode("utf-8"), mode_reference_path=base_path),
        stdout=True,
    )

    assert fake_stdout.getvalue() == "snowman ☃"


def test_emit_transform_output_skips_rewrite_when_reusing_same_compare_path(
    tmp_path: Path,
) -> None:
    reference_path = tmp_path / "reference"
    output_path = tmp_path / "output"
    reference_path.write_text("ref\n", encoding="utf-8")
    output_path.write_text("keep\n", encoding="utf-8")
    output_path.chmod(0o600)
    output_path.touch()
    original_mtime = output_path.stat().st_mtime_ns

    MODULE.emit_transform_output(
        output_path,
        MODULE.TransformOutput(
            content="keep\n",
            mode_reference_path=reference_path,
            reused_compare_path=output_path,
        ),
    )

    assert output_path.read_text(encoding="utf-8") == "keep\n"
    assert output_path.stat().st_mtime_ns == original_mtime
    assert output_path.stat().st_mode & 0o777 == reference_path.stat().st_mode & 0o777

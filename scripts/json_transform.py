#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from scripts.transform_cli import run_engine_cli
from scripts.transform_engine import (
    BaseTransformEngine,
    SelectorAction,
    SelectorSpec,
    TransformMode,
    TransformRequest,
)


JsonDict = dict[str, Any]


def load_json(path: Path) -> JsonDict:
    if not path.exists():
        return {}

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected top-level JSON object in {path}")
    return loaded


def filter_retained_keys(data: JsonDict, retained_keys: tuple[str, ...]) -> JsonDict:
    if not retained_keys:
        return dict(data)
    return {key: data[key] for key in retained_keys if key in data}


def filter_stripped_keys(data: JsonDict, stripped_keys: tuple[str, ...]) -> JsonDict:
    if not stripped_keys:
        return dict(data)
    stripped_key_set = set(stripped_keys)
    return {key: value for key, value in data.items() if key not in stripped_key_set}


def select_json_data(
    data: JsonDict,
    selector_action: SelectorAction,
    selected_keys: tuple[str, ...],
) -> JsonDict:
    if selector_action == SelectorAction.REMOVE:
        return filter_stripped_keys(data, selected_keys)
    return filter_retained_keys(data, selected_keys)


def overlay_json_data(base_data: JsonDict, overlay_data: JsonDict) -> JsonDict:
    merged_data = dict(base_data)
    merged_data.update(overlay_data)
    return merged_data


def json_text(data: JsonDict) -> str:
    return json.dumps(data, indent="\t", ensure_ascii=False) + "\n"


def get_existing_text_if_semantically_unchanged(path: Path, data: JsonDict) -> str | None:
    if not path.exists():
        return None

    existing_text = path.read_text(encoding="utf-8")
    try:
        existing_data = json.loads(existing_text)
    except Exception:
        return None

    if existing_data != data:
        return None

    return existing_text


def mirror_mode(reference_path: Path, output_path: Path) -> None:
    if not reference_path.exists() or not output_path.exists():
        return
    output_path.chmod(reference_path.stat().st_mode & 0o777)


def write_json_if_changed(
    output_path: Path | None,
    data: JsonDict,
    mode_reference_path: Path,
    compare_path: Path | None,
    stdout: bool = False,
) -> None:
    if compare_path is not None:
        existing_text = get_existing_text_if_semantically_unchanged(compare_path, data)
        if existing_text is not None:
            if stdout:
                sys.stdout.write(existing_text)
            else:
                assert output_path is not None
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(existing_text, encoding="utf-8")
                if mode_reference_path != output_path:
                    mirror_mode(mode_reference_path, output_path)
            return

    serialized_text = json_text(data)
    if stdout:
        sys.stdout.write(serialized_text)
        return

    assert output_path is not None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized_text, encoding="utf-8")
    if mode_reference_path != output_path:
        mirror_mode(mode_reference_path, output_path)


class JsonTransformEngine(BaseTransformEngine):
    name = "json"
    SELECTOR_SPECS = (
        SelectorSpec(
            name="key",
            prefix="exact",
            is_default=True,
            description="exact top-level JSON object key",
            examples=("buildDir", "version"),
        ),
    )

    def requires_selectors(self) -> bool:
        return False

    def configure_parser(self, parser) -> None:
        parser.add_argument(
            "--compare-file",
            type=Path,
            help="Optional JSON file to compare against for semantic no-op text reuse.",
        )

    def build_engine_options(self, parsed_args) -> dict[str, Any]:
        return {
            "compare_path": parsed_args.compare_file,
            "stdout": parsed_args.stdout,
        }

    def transform(self, request: TransformRequest) -> None:
        self.validate_request(request)
        selected_keys = request.selector_values("key")

        base_data = load_json(request.base_path)
        transformed_data = select_json_data(
            base_data,
            request.selector_action,
            selected_keys,
        )

        if request.mode == TransformMode.MERGE:
            assert request.overlay_path is not None
            overlay_data = load_json(request.overlay_path)
            transformed_data = overlay_json_data(transformed_data, overlay_data)

        write_json_if_changed(
            request.output_path,
            transformed_data,
            mode_reference_path=request.base_path,
            compare_path=request.engine_option("compare_path"),
            stdout=bool(request.engine_option("stdout", False)),
        )


def main(argv: list[str] | None = None) -> int:
    return run_engine_cli(JsonTransformEngine(), argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

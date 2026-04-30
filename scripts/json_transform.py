#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from scripts.transform_cli import run_engine_cli
from scripts.transform_engine import (
    BaseTransformEngine,
    SelectorAction,
    SelectorSpec,
    TransformMode,
    TransformOutput,
    TransformRequest,
    compile_selector_regexes,
    emit_transform_output,
)


JsonDict = dict[str, Any]
KeyRegex = re.Pattern[str]


def load_json(path: Path) -> JsonDict:
    if not path.exists():
        return {}

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected top-level JSON object in {path}")
    return loaded



def compile_key_regexes(raw_key_regexes: tuple[str, ...]) -> tuple[KeyRegex, ...]:
    return compile_selector_regexes(raw_key_regexes, "JSON key selector")



def filter_retained_keys(
    data: JsonDict,
    retained_keys: tuple[str, ...],
    retained_key_regexes: tuple[KeyRegex, ...] = (),
) -> JsonDict:
    if not retained_keys and not retained_key_regexes:
        return dict(data)
    retained_key_set = set(retained_keys)
    return {
        key: value
        for key, value in data.items()
        if key in retained_key_set
        or any(key_regex.search(key) for key_regex in retained_key_regexes)
    }



def filter_stripped_keys(
    data: JsonDict,
    stripped_keys: tuple[str, ...],
    stripped_key_regexes: tuple[KeyRegex, ...] = (),
) -> JsonDict:
    if not stripped_keys and not stripped_key_regexes:
        return dict(data)
    stripped_key_set = set(stripped_keys)
    return {
        key: value
        for key, value in data.items()
        if key not in stripped_key_set
        and not any(key_regex.search(key) for key_regex in stripped_key_regexes)
    }



def select_json_data(
    data: JsonDict,
    selector_action: SelectorAction,
    selected_keys: tuple[str, ...],
    selected_key_regexes: tuple[KeyRegex, ...] = (),
) -> JsonDict:
    if selector_action == SelectorAction.REMOVE:
        return filter_stripped_keys(data, selected_keys, selected_key_regexes)
    return filter_retained_keys(data, selected_keys, selected_key_regexes)



def overlay_json_data(
    original_base_data: JsonDict,
    preserved_base_data: JsonDict,
    overlay_data: JsonDict,
) -> JsonDict:
    merged_data: JsonDict = {}

    # Keep surviving keys in live order so repo-managed value changes do not also
    # produce noisy key-movement diffs.
    for key in original_base_data:
        if key in overlay_data:
            merged_data[key] = overlay_data[key]
            continue
        if key in preserved_base_data:
            merged_data[key] = preserved_base_data[key]

    for source_data in (overlay_data, preserved_base_data):
        for key, value in source_data.items():
            if key in merged_data:
                continue
            merged_data[key] = value

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



def build_json_output(
    data: JsonDict,
    *,
    mode_reference_path: Path,
    compare_path: Path | None = None,
) -> TransformOutput:
    if compare_path is not None:
        existing_text = get_existing_text_if_semantically_unchanged(compare_path, data)
        if existing_text is not None:
            return TransformOutput(
                content=existing_text,
                mode_reference_path=mode_reference_path,
                reused_compare_path=compare_path,
            )

    return TransformOutput(
        content=json_text(data),
        mode_reference_path=mode_reference_path,
    )



def write_json_if_changed(
    output_path: Path | None,
    data: JsonDict,
    mode_reference_path: Path,
    compare_path: Path | None,
    stdout: bool = False,
) -> None:
    emit_transform_output(
        output_path,
        build_json_output(
            data,
            mode_reference_path=mode_reference_path,
            compare_path=compare_path,
        ),
        stdout=stdout,
    )


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
        SelectorSpec(
            name="key_regex",
            prefix="re",
            description="regex matching top-level JSON object keys",
            examples=(r"^build", r"Dir$"),
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

    def validate_request(self, request: TransformRequest) -> None:
        super().validate_request(request)
        compile_key_regexes(request.selector_values("key_regex"))

    def transform(self, request: TransformRequest) -> TransformOutput:
        self.validate_request(request)
        selected_keys = request.selector_values("key")
        selected_key_regexes = compile_key_regexes(request.selector_values("key_regex"))

        base_data = load_json(request.base_path)
        transformed_data = select_json_data(
            base_data,
            request.selector_action,
            selected_keys,
            selected_key_regexes,
        )

        if request.mode == TransformMode.MERGE:
            assert request.overlay_path is not None
            overlay_data = load_json(request.overlay_path)
            transformed_data = overlay_json_data(base_data, transformed_data, overlay_data)

        return build_json_output(
            transformed_data,
            mode_reference_path=request.base_path,
            compare_path=request.engine_option("compare_path"),
        )



def main(argv: list[str] | None = None) -> int:
    return run_engine_cli(JsonTransformEngine(), argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import plistlib
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


PlistDict = dict[str, Any]
KeyRegex = re.Pattern[str]


def load_plist(path: Path) -> PlistDict:
    if not path.exists():
        return {}

    with path.open("rb") as handle:
        loaded = plistlib.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError(f"Expected plist dictionary in {path}")

    return loaded



def compile_key_regexes(raw_key_regexes: tuple[str, ...]) -> tuple[KeyRegex, ...]:
    return compile_selector_regexes(raw_key_regexes, "plist key selector")



def filter_retained_keys(
    data: PlistDict,
    retained_keys: tuple[str, ...],
    retained_key_regexes: tuple[KeyRegex, ...] = (),
) -> PlistDict:
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
    data: PlistDict,
    stripped_keys: tuple[str, ...],
    stripped_key_regexes: tuple[KeyRegex, ...] = (),
) -> PlistDict:
    if not stripped_keys and not stripped_key_regexes:
        return dict(data)
    stripped_key_set = set(stripped_keys)
    return {
        key: value
        for key, value in data.items()
        if key not in stripped_key_set
        and not any(key_regex.search(key) for key_regex in stripped_key_regexes)
    }



def select_plist_data(
    data: PlistDict,
    selector_action: SelectorAction,
    selected_keys: tuple[str, ...],
    selected_key_regexes: tuple[KeyRegex, ...] = (),
) -> PlistDict:
    if selector_action == SelectorAction.REMOVE:
        return filter_stripped_keys(data, selected_keys, selected_key_regexes)
    return filter_retained_keys(data, selected_keys, selected_key_regexes)



def overlay_plist_data(base_data: PlistDict, overlay_data: PlistDict) -> PlistDict:
    merged_data = dict(base_data)
    merged_data.update(overlay_data)
    return merged_data



def plist_format_from_name(format_name: str) -> int:
    return plistlib.FMT_XML if format_name == "xml" else plistlib.FMT_BINARY



def write_plist(path: Path, data: PlistDict, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(data, handle, fmt=plist_format_from_name(fmt), sort_keys=True)



def plist_bytes(data: PlistDict, fmt: str) -> bytes:
    return plistlib.dumps(data, fmt=plist_format_from_name(fmt), sort_keys=True)



def get_existing_bytes_if_semantically_unchanged(
    path: Path,
    data: PlistDict,
) -> bytes | None:
    if not path.exists():
        return None

    existing_bytes = path.read_bytes()
    try:
        existing_data = plistlib.loads(existing_bytes)
    except Exception:
        return None

    if existing_data != data:
        return None

    return existing_bytes



def build_plist_output(
    data: PlistDict,
    output_format: str,
    *,
    mode_reference_path: Path,
    compare_path: Path | None,
) -> TransformOutput:
    if compare_path is not None:
        existing_bytes = get_existing_bytes_if_semantically_unchanged(compare_path, data)
        if existing_bytes is not None:
            return TransformOutput(
                content=existing_bytes,
                mode_reference_path=mode_reference_path,
                reused_compare_path=compare_path,
            )

    return TransformOutput(
        content=plist_bytes(data, output_format),
        mode_reference_path=mode_reference_path,
    )



def write_plist_if_changed(
    output_path: Path | None,
    data: PlistDict,
    output_format: str,
    mode_reference_path: Path,
    compare_path: Path | None,
    stdout: bool = False,
) -> None:
    emit_transform_output(
        output_path,
        build_plist_output(
            data,
            output_format,
            mode_reference_path=mode_reference_path,
            compare_path=compare_path,
        ),
        stdout=stdout,
    )


class PlistTransformEngine(BaseTransformEngine):
    name = "plist"
    SELECTOR_SPECS = (
        SelectorSpec(
            name="key",
            prefix="exact",
            is_default=True,
            description="exact top-level plist dictionary key",
            examples=("NSUserKeyEquivalents", "bypassEventsFromOtherApplications"),
        ),
        SelectorSpec(
            name="key_regex",
            prefix="re",
            description="regex matching top-level plist dictionary keys",
            examples=(r"^NS", r"Window"),
        ),
    )

    def requires_selectors(self) -> bool:
        return False

    def configure_parser(self, parser) -> None:
        parser.add_argument(
            "--compare-file",
            type=Path,
            help="Optional plist to compare against for semantic no-op byte reuse.",
        )
        parser.add_argument(
            "--output-format",
            choices=("xml", "binary"),
            default="xml",
            help="Serialization format for the output plist.",
        )

    def build_engine_options(self, parsed_args) -> dict[str, Any]:
        return {
            "compare_path": parsed_args.compare_file,
            "output_format": parsed_args.output_format,
            "stdout": parsed_args.stdout,
        }

    def validate_request(self, request: TransformRequest) -> None:
        super().validate_request(request)
        compile_key_regexes(request.selector_values("key_regex"))

    def transform(self, request: TransformRequest) -> TransformOutput:
        self.validate_request(request)
        selected_keys = request.selector_values("key")
        selected_key_regexes = compile_key_regexes(request.selector_values("key_regex"))
        output_format = str(request.engine_option("output_format", "xml"))

        base_data = load_plist(request.base_path)
        transformed_data = select_plist_data(
            base_data,
            request.selector_action,
            selected_keys,
            selected_key_regexes,
        )

        if request.mode == TransformMode.MERGE:
            assert request.overlay_path is not None
            overlay_data = load_plist(request.overlay_path)
            transformed_data = overlay_plist_data(transformed_data, overlay_data)

        return build_plist_output(
            transformed_data,
            output_format,
            mode_reference_path=request.base_path,
            compare_path=request.engine_option("compare_path"),
        )



def main(argv: list[str] | None = None) -> int:
    return run_engine_cli(PlistTransformEngine(), argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

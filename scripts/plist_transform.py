#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import plistlib
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.transform_cli import run_engine_cli  # noqa: E402
from scripts.transform_engine import (  # noqa: E402
    BaseTransformEngine,
    SelectorAction,
    SelectorSpec,
    TransformMode,
    TransformRequest,
)


PlistDict = dict[str, Any]


def load_plist(path: Path) -> PlistDict:
    if not path.exists():
        return {}

    with path.open("rb") as handle:
        loaded = plistlib.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError(f"Expected plist dictionary in {path}")

    return loaded


def filter_retained_keys(data: PlistDict, retained_keys: tuple[str, ...]) -> PlistDict:
    if not retained_keys:
        return dict(data)
    return {key: data[key] for key in retained_keys if key in data}


def filter_stripped_keys(data: PlistDict, stripped_keys: tuple[str, ...]) -> PlistDict:
    if not stripped_keys:
        return dict(data)
    stripped_key_set = set(stripped_keys)
    return {key: value for key, value in data.items() if key not in stripped_key_set}


def select_plist_data(
    data: PlistDict,
    selector_action: SelectorAction,
    selected_keys: tuple[str, ...],
) -> PlistDict:
    if selector_action == SelectorAction.REMOVE:
        return filter_stripped_keys(data, selected_keys)
    return filter_retained_keys(data, selected_keys)


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


def mirror_mode(reference_path: Path, output_path: Path) -> None:
    if not reference_path.exists() or not output_path.exists():
        return
    output_path.chmod(reference_path.stat().st_mode & 0o777)


def write_plist_if_changed(
    output_path: Path | None,
    data: PlistDict,
    output_format: str,
    mode_reference_path: Path,
    compare_path: Path | None,
    stdout: bool = False,
) -> None:
    if compare_path is not None:
        existing_bytes = get_existing_bytes_if_semantically_unchanged(compare_path, data)
        if existing_bytes is not None:
            if stdout:
                sys.stdout.buffer.write(existing_bytes)
            else:
                assert output_path is not None
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(existing_bytes)
                if mode_reference_path != output_path:
                    mirror_mode(mode_reference_path, output_path)
            return

    if stdout:
        sys.stdout.buffer.write(plist_bytes(data, output_format))
        return

    assert output_path is not None
    write_plist(output_path, data, output_format)
    if mode_reference_path != output_path:
        mirror_mode(mode_reference_path, output_path)


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

    def transform(self, request: TransformRequest) -> None:
        self.validate_request(request)
        selected_keys = request.selector_values("key")
        output_format = str(request.engine_option("output_format", "xml"))

        base_data = load_plist(request.base_path)
        transformed_data = select_plist_data(
            base_data,
            request.selector_action,
            selected_keys,
        )

        mode_reference_path = request.base_path
        if request.mode == TransformMode.MERGE:
            assert request.overlay_path is not None
            overlay_data = load_plist(request.overlay_path)
            transformed_data = overlay_plist_data(transformed_data, overlay_data)

        compare_path = request.engine_option("compare_path")

        write_plist_if_changed(
            request.output_path,
            transformed_data,
            output_format,
            mode_reference_path=mode_reference_path,
            compare_path=compare_path,
            stdout=bool(request.engine_option("stdout", False)),
        )


def main(argv: list[str] | None = None) -> int:
    return run_engine_cli(PlistTransformEngine(), argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

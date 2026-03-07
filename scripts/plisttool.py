#!/usr/bin/env python3

import argparse
import os
import pathlib
import plistlib
from typing import Any


def load_plist(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("rb") as handle:
        loaded = plistlib.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError(f"Expected plist dictionary in {path}")

    return loaded


def filter_keys(data: dict[str, Any], keep_keys: list[str]) -> dict[str, Any]:
    return {key: data[key] for key in keep_keys if key in data}


def write_plist(path: pathlib.Path, data: dict[str, Any], fmt: str) -> None:
    plist_format = plistlib.FMT_XML if fmt == "xml" else plistlib.FMT_BINARY
    with path.open("wb") as handle:
        plistlib.dump(data, handle, fmt=plist_format, sort_keys=True)


def get_existing_bytes_if_semantically_unchanged(
    path: pathlib.Path, data: dict[str, Any]
) -> bytes | None:
    if not path.exists():
        return None

    with path.open("rb") as handle:
        existing_bytes = handle.read()

    try:
        existing_data = plistlib.loads(existing_bytes)
    except Exception:
        return None

    if existing_data != data:
        return None

    return existing_bytes


def mirror_mode(src: pathlib.Path, dst: pathlib.Path) -> None:
    if not src.exists() or not dst.exists():
        return
    os.chmod(dst, src.stat().st_mode & 0o777)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Filter or merge plist dictionaries for dotdrop transforms."
    )
    parser.add_argument("input_file", help="Source plist file")
    parser.add_argument("output_file", help="Output plist file")
    parser.add_argument(
        "--keep-key",
        action="append",
        default=[],
        dest="keep_keys",
        help="Dictionary key to preserve from the input plist. May be passed multiple times.",
    )
    parser.add_argument(
        "--merge-file",
        help="Existing plist to merge preserved keys into before writing output.",
    )
    parser.add_argument(
        "--compare-file",
        help="Existing plist whose bytes should be preserved when data is unchanged.",
    )
    parser.add_argument(
        "--output-format",
        choices=("xml", "binary"),
        default="xml",
        help="Serialization format for the output plist.",
    )
    args = parser.parse_args()

    input_path = pathlib.Path(args.input_file)
    output_path = pathlib.Path(args.output_file)

    source_data = load_plist(input_path)
    filtered_data = (
        filter_keys(source_data, args.keep_keys) if args.keep_keys else dict(source_data)
    )

    if args.merge_file:
        merged_data = load_plist(pathlib.Path(args.merge_file))
        merged_data.update(filtered_data)
        filtered_data = merged_data

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # For install transforms we merge managed keys into the existing destination plist.
    # If that merge is semantically unchanged, preserve the destination bytes exactly
    # so dotdrop does not see no-op rewrites caused by plistlib re-serialization.
    compare_path = (
        pathlib.Path(args.compare_file)
        if args.compare_file
        else pathlib.Path(args.merge_file)
        if args.merge_file
        else output_path
    )
    existing_bytes = get_existing_bytes_if_semantically_unchanged(
        compare_path, filtered_data
    )
    if existing_bytes is not None:
        with output_path.open("wb") as handle:
            handle.write(existing_bytes)
        if compare_path != output_path:
            mirror_mode(compare_path, output_path)
        return 0
    write_plist(output_path, filtered_data, args.output_format)
    if compare_path != output_path:
        mirror_mode(compare_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

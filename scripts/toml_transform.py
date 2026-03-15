#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomllib


def load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("rb") as file:
        data = tomllib.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a TOML table at the root")

    return data


def sync_mode(path: Path, reference_path: Path) -> None:
    if not path.exists() or not reference_path.exists():
        return

    target_mode = reference_path.stat().st_mode & 0o777
    current_mode = path.stat().st_mode & 0o777
    if current_mode != target_mode:
        path.chmod(target_mode)


def write_text_if_changed(path: Path, content: str, reference_path: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        if reference_path is not None:
            sync_mode(path, reference_path)
        return
    path.write_text(content, encoding="utf-8")
    if reference_path is not None:
        sync_mode(path, reference_path)


def matches_table_regex(table_path: tuple[str, ...], table_regexes: list[re.Pattern[str]]) -> bool:
    raw_table_path = ".".join(table_path)
    return any(table_regex.search(raw_table_path) for table_regex in table_regexes)


def strip_keys_text(
    input_path: Path,
    output_path: Path,
    key_paths: list[tuple[str, ...]],
    table_regexes_to_strip: list[re.Pattern[str]],
) -> None:
    # This line-based transformer preserves comments and formatting, but it only
    # safely edits existing single-line assignments. If we need robust multiline
    # TOML value handling later, switch this script to a comment-preserving TOML
    # library instead of extending regex edits further.
    key_paths_by_table: dict[tuple[str, ...], set[str]] = {}
    for key_path in key_paths:
        table_path, key_name = split_key_path(key_path)
        key_paths_by_table.setdefault(table_path, set()).add(key_name)

    lines = input_path.read_text(encoding="utf-8").splitlines(keepends=True)
    stripped_lines: list[str] = []
    current_table_path: tuple[str, ...] = ()
    skip_current_table = False

    for line in lines:
        header_match = re.match(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$", line)
        if header_match:
            current_table_path = parse_key_path(header_match.group(1))
            skip_current_table = matches_table_regex(current_table_path, table_regexes_to_strip)
            if skip_current_table:
                continue
            stripped_lines.append(line)
            continue

        if skip_current_table:
            continue

        target_keys = key_paths_by_table.get(current_table_path)
        if target_keys is None:
            stripped_lines.append(line)
            continue

        assignment_match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line)
        if assignment_match and assignment_match.group(1) in target_keys:
            continue

        stripped_lines.append(line)

    write_text_if_changed(output_path, "".join(stripped_lines), reference_path=input_path)


def merge_keys_text(
    input_path: Path,
    output_path: Path,
    merge_config: Mapping[str, Any],
    key_paths: list[tuple[str, ...]],
) -> None:
    lines = output_path.read_text(encoding="utf-8").splitlines(keepends=True)

    for key_path in key_paths:
        merged_value = get_value(merge_config, key_path)
        if merged_value is None:
            continue
        lines = merge_key_into_lines(lines, key_path, merged_value)

    write_text_if_changed(output_path, "".join(lines), reference_path=input_path)


def parse_key_path(raw_key: str) -> tuple[str, ...]:
    key_path = tuple(part.strip() for part in raw_key.split(".") if part.strip())
    if not key_path:
        raise ValueError("key paths must not be empty")
    return key_path


def split_key_path(key_path: tuple[str, ...]) -> tuple[tuple[str, ...], str]:
    return key_path[:-1], key_path[-1]


def get_table(config: Mapping[str, Any], table_path: tuple[str, ...]) -> Mapping[str, Any] | None:
    current: Any = config
    for part in table_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)

    if not isinstance(current, Mapping):
        return None

    return current


def get_mutable_table(config: dict[str, Any], table_path: tuple[str, ...]) -> dict[str, Any] | None:
    current: Any = config
    for part in table_path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if not isinstance(current, dict):
            return None

    if not isinstance(current, dict):
        return None

    return current


def get_value(config: Mapping[str, Any], key_path: tuple[str, ...]) -> Any | None:
    table_path, key_name = split_key_path(key_path)
    table = get_table(config, table_path)
    if table is None or key_name not in table:
        return None
    return table[key_name]


def merge_key_into_lines(
    lines: list[str],
    key_path: tuple[str, ...],
    value: Any,
) -> list[str]:
    table_path, key_name = split_key_path(key_path)
    start_index, end_index = find_table_bounds(lines, table_path)
    if start_index is None or end_index is None:
        return lines

    assignment_lines = render_assignment_lines(key_name, value)
    assignment_pattern = re.compile(rf"^\s*{re.escape(key_name)}\s*=")

    for line_index in range(start_index, end_index):
        if assignment_pattern.match(lines[line_index]):
            return lines[:line_index] + assignment_lines + lines[line_index + 1 :]

    insert_index = end_index
    while insert_index > start_index and lines[insert_index - 1].strip() == "":
        insert_index -= 1

    prefix = [] if insert_index == 0 or lines[insert_index - 1].endswith("\n") else ["\n"]
    suffix = [] if insert_index >= len(lines) or lines[insert_index].strip() == "" else ["\n"]
    return lines[:insert_index] + prefix + assignment_lines + suffix + lines[insert_index:]


def find_table_bounds(
    lines: list[str],
    table_path: tuple[str, ...],
) -> tuple[int | None, int | None]:
    if not table_path:
        for index, line in enumerate(lines):
            if re.match(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$", line):
                return 0, index
        return 0, len(lines)

    current_table_path: tuple[str, ...] | None = ()
    section_start: int | None = None

    for index, line in enumerate(lines):
        header_match = re.match(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$", line)
        if not header_match:
            continue

        current_table_path = parse_key_path(header_match.group(1))
        if section_start is not None:
            return section_start, index

        if current_table_path == table_path:
            section_start = index + 1

    if section_start is not None:
        return section_start, len(lines)

    return None, None


def render_assignment_lines(key_name: str, value: Any) -> list[str]:
    rendered_assignment = f"{key_name} = {render_toml_value(value)}\n"
    return rendered_assignment.splitlines(keepends=True)


def render_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return render_toml_string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "nan"
        if value == float("inf"):
            return "inf"
        if value == float("-inf"):
            return "-inf"
        return repr(value)
    if isinstance(value, dt.datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(render_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        items = ", ".join(
            f"{render_inline_key(str(key))} = {render_toml_value(item)}"
            for key, item in value.items()
        )
        return "{ " + items + " }"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def render_toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\f", "\\f")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def render_inline_key(value: str) -> str:
    if re.match(r"^[A-Za-z0-9_-]+$", value):
        return value
    return render_toml_string(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Strip or merge selected TOML keys for dotdrop transformers."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("selectors", nargs="*")
    parser.add_argument("--mode", choices=["strip", "merge"], required=True)
    parser.add_argument("--merge-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.selectors:
        raise ValueError("at least one selector is required")

    raw_key_paths = [selector for selector in args.selectors if not selector.startswith("re:")]
    raw_table_regexes = [selector[3:] for selector in args.selectors if selector.startswith("re:")]

    key_paths = [parse_key_path(raw_key) for raw_key in raw_key_paths]
    table_regexes_to_strip = [re.compile(raw_regex) for raw_regex in raw_table_regexes]

    if args.mode == "strip":
        strip_keys_text(args.input_path, args.output_path, key_paths, table_regexes_to_strip)
        return 0

    if args.merge_file is None:
        raise ValueError("--merge-file is required when --mode=merge")

    merge_config = load_toml(args.input_path)
    if args.merge_file.exists():
        write_text_if_changed(
            args.output_path,
            args.merge_file.read_text(encoding="utf-8"),
            reference_path=args.merge_file,
        )
    else:
        write_text_if_changed(
            args.output_path,
            args.input_path.read_text(encoding="utf-8"),
            reference_path=args.input_path,
        )
    merge_keys_text(args.input_path, args.output_path, merge_config, key_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

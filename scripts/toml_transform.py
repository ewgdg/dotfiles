#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument


TomlContainer = TOMLDocument | Table


def load_document(path: Path) -> TOMLDocument:
    if not path.exists():
        return tomlkit.document()
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def sync_mode(path: Path, reference_path: Path) -> None:
    if not path.exists() or not reference_path.exists():
        return

    target_mode = reference_path.stat().st_mode & 0o777
    current_mode = path.stat().st_mode & 0o777
    if current_mode != target_mode:
        path.chmod(target_mode)


def write_document_if_changed(path: Path, doc: TOMLDocument, reference_path: Path) -> None:
    content = doc.as_string()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        sync_mode(path, reference_path)
        return
    path.write_text(content, encoding="utf-8")
    sync_mode(path, reference_path)


def parse_key_path(raw_key: str) -> tuple[str, ...]:
    key_path = tuple(split_toml_key(raw_key))
    if not key_path:
        raise ValueError("key paths must not be empty")
    return key_path


def split_toml_key(raw_key: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    escape = False

    for char in raw_key:
        if in_quotes and escape:
            current.append(char)
            escape = False
            continue

        if in_quotes and char == "\\":
            escape = True
            continue

        if char == '"':
            in_quotes = not in_quotes
            continue

        if char == "." and not in_quotes:
            append_key_part(parts, current)
            current = []
            continue

        current.append(char)

    if in_quotes:
        raise ValueError(f"unterminated quoted TOML key: {raw_key}")

    append_key_part(parts, current)
    return parts


def append_key_part(parts: list[str], current: list[str]) -> None:
    raw_part = "".join(current).strip()
    if not raw_part:
        return
    if raw_part.startswith('"') and raw_part.endswith('"'):
        parts.append(bytes(raw_part[1:-1], "utf-8").decode("unicode_escape"))
        return
    parts.append(raw_part)


def split_key_path(key_path: tuple[str, ...]) -> tuple[tuple[str, ...], str]:
    return key_path[:-1], key_path[-1]


def get_container(root: TomlContainer, table_path: tuple[str, ...]) -> TomlContainer | None:
    current: Any = root
    for part in table_path:
        if part not in current:
            return None
        current = current[part]
        if not isinstance(current, Table):
            return None
    return current


def path_exists(root: TomlContainer, key_path: tuple[str, ...]) -> bool:
    table_path, key_name = split_key_path(key_path)
    container = get_container(root, table_path)
    return container is not None and key_name in container


def get_key_path_value(root: TomlContainer, key_path: tuple[str, ...]) -> Any | None:
    table_path, key_name = split_key_path(key_path)
    container = get_container(root, table_path)
    if container is None or key_name not in container:
        return None
    return container[key_name]


def delete_key_path(root: TomlContainer, key_path: tuple[str, ...]) -> None:
    table_path, key_name = split_key_path(key_path)
    container = get_container(root, table_path)
    if container is not None and key_name in container:
        del container[key_name]


def iter_table_paths(root: TomlContainer, prefix: tuple[str, ...] = ()) -> Iterable[tuple[str, ...]]:
    for key, value in root.items():
        if not isinstance(value, Table):
            continue
        key_path = prefix + (str(key),)
        yield key_path
        yield from iter_table_paths(value, key_path)


def matches_table_regex(table_path: tuple[str, ...], table_regexes: list[re.Pattern[str]]) -> bool:
    raw_table_path = ".".join(table_path)
    return any(table_regex.search(raw_table_path) for table_regex in table_regexes)


def normalize_blank_lines(content: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", content)


def ensure_container(root: TomlContainer, table_path: tuple[str, ...]) -> TomlContainer:
    current: TomlContainer = root
    for part in table_path:
        next_value = current.get(part)
        if not isinstance(next_value, Table):
            current[part] = tomlkit.table()
            next_value = current[part]
        current = next_value
    return current


def strip_keys(
    input_path: Path,
    output_path: Path,
    key_paths: list[tuple[str, ...]],
    table_regexes_to_strip: list[re.Pattern[str]],
) -> None:
    doc = load_document(input_path)
    table_paths = sorted(iter_table_paths(doc), key=len, reverse=True)
    for table_path in table_paths:
        if matches_table_regex(table_path, table_regexes_to_strip):
            delete_key_path(doc, table_path)

    for key_path in key_paths:
        delete_key_path(doc, key_path)

    normalized_doc = tomlkit.parse(normalize_blank_lines(doc.as_string()))
    write_document_if_changed(output_path, normalized_doc, reference_path=input_path)


def overlay_preserved_keys(
    source_doc: TomlContainer,
    target_doc: TomlContainer,
    preserved_key_paths: set[tuple[str, ...]],
) -> None:
    for key_path in sorted(preserved_key_paths, key=len):
        preserved_value = get_key_path_value(source_doc, key_path)
        if preserved_value is None:
            continue

        table_path, key_name = split_key_path(key_path)
        target_container = ensure_container(target_doc, table_path)
        target_container[key_name] = copy.deepcopy(preserved_value)


def merge_keys(
    input_path: Path,
    output_path: Path,
    merge_file: Path,
    preserved_key_paths: set[tuple[str, ...]],
) -> None:
    repo_doc = load_document(input_path)
    merged_doc = copy.deepcopy(repo_doc)
    if merge_file.exists():
        local_doc = load_document(merge_file)
        overlay_preserved_keys(local_doc, merged_doc, preserved_key_paths)
    write_document_if_changed(output_path, merged_doc, reference_path=input_path)


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
        strip_keys(args.input_path, args.output_path, key_paths, table_regexes_to_strip)
        return 0

    if args.merge_file is None:
        raise ValueError("--merge-file is required when --mode=merge")

    merge_keys(args.input_path, args.output_path, args.merge_file, set(key_paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

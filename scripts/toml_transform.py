#!/usr/bin/env python3

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from pathlib import Path
import sys
from typing import Any

import tomlkit
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument


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


def get_existing_text_if_unchanged(compare_path: Path, content: str) -> str | None:
    if not compare_path.exists():
        return None

    existing_content = compare_path.read_text(encoding="utf-8")
    if existing_content != content:
        return None

    return existing_content


def write_document_if_changed(
    path: Path,
    doc: TOMLDocument,
    mode_reference_path: Path,
    compare_path: Path | None = None,
 ) -> None:
    content = doc.as_string()
    path.parent.mkdir(parents=True, exist_ok=True)
    if compare_path is not None:
        existing_content = get_existing_text_if_unchanged(compare_path, content)
        if existing_content is not None:
            if compare_path != path:
                path.write_text(existing_content, encoding="utf-8")
            sync_mode(path, mode_reference_path)
            return
    path.write_text(content, encoding="utf-8")
    sync_mode(path, mode_reference_path)


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


def iter_item_paths_in_order(
    root: TomlContainer,
    prefix: tuple[str, ...] = (),
) -> Iterable[tuple[str, ...]]:
    for key, value in root.items():
        key_path = prefix + (str(key),)
        yield key_path
        if isinstance(value, Table):
            yield from iter_item_paths_in_order(value, key_path)


def matches_table_regex(table_path: tuple[str, ...], table_regexes: list[re.Pattern[str]]) -> bool:
    raw_table_path = ".".join(table_path)
    return any(table_regex.search(raw_table_path) for table_regex in table_regexes)


def parse_key_paths(raw_key_paths: Iterable[str]) -> list[tuple[str, ...]]:
    return [parse_key_path(raw_key) for raw_key in raw_key_paths]


def compile_table_regexes(raw_table_regexes: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(raw_regex) for raw_regex in raw_table_regexes]


def normalize_blank_lines(content: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", content)


def normalize_document(doc: TOMLDocument) -> TOMLDocument:
    return tomlkit.parse(normalize_blank_lines(doc.as_string()))


def ensure_container(root: TomlContainer, table_path: tuple[str, ...]) -> TomlContainer:
    current: TomlContainer = root
    for part in table_path:
        next_value = current.get(part)
        if not isinstance(next_value, Table):
            current[part] = tomlkit.table()
            next_value = current[part]
        current = next_value
    return current


def build_document_with_stripped_matchers(
    source_doc: TOMLDocument,
    stripped_key_paths: list[tuple[str, ...]],
    stripped_table_regexes: list[re.Pattern[str]],
) -> TOMLDocument:
    stripped_doc = copy.deepcopy(source_doc)
    table_paths = sorted(iter_table_paths(stripped_doc), key=len, reverse=True)
    for table_path in table_paths:
        if matches_table_regex(table_path, stripped_table_regexes):
            delete_key_path(stripped_doc, table_path)

    for key_path in stripped_key_paths:
        delete_key_path(stripped_doc, key_path)

    return normalize_document(stripped_doc)


def strip_keys(
    base_path: Path,
    output_path: Path,
    stripped_key_paths: list[tuple[str, ...]],
    stripped_table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
 ) -> None:
    normalized_doc = build_document_with_stripped_matchers(
        load_document(base_path),
        stripped_key_paths,
        stripped_table_regexes,
    )
    write_document_if_changed(
        output_path,
        normalized_doc,
        mode_reference_path=base_path,
        compare_path=compare_path,
    )


def overlay_preserved_keys(
    overlay_doc: TomlContainer,
    base_doc: TomlContainer,
    retained_key_paths: Iterable[tuple[str, ...]],
) -> None:
    retained_key_path_set = set(retained_key_paths)
    for key_path in iter_item_paths_in_order(overlay_doc):
        if key_path not in retained_key_path_set:
            continue
        retained_value = get_key_path_value(overlay_doc, key_path)
        if retained_value is None:
            continue

        table_path, key_name = split_key_path(key_path)
        target_container = ensure_container(base_doc, table_path)
        target_container[key_name] = copy.deepcopy(retained_value)


def overlay_preserved_tables(
    overlay_doc: TomlContainer,
    base_doc: TomlContainer,
    retained_table_regexes: list[re.Pattern[str]],
) -> None:
    if not retained_table_regexes:
        return

    for table_path in sorted(iter_table_paths(overlay_doc), key=len):
        if not matches_table_regex(table_path, retained_table_regexes):
            continue

        retained_table = get_key_path_value(overlay_doc, table_path)
        if retained_table is None:
            continue

        parent_path, table_name = split_key_path(table_path)
        target_container = ensure_container(base_doc, parent_path)
        target_container[table_name] = copy.deepcopy(retained_table)


def build_document_with_retained_matchers(
    source_doc: TOMLDocument,
    retained_key_paths: Iterable[tuple[str, ...]],
    retained_table_regexes: list[re.Pattern[str]],
) -> TOMLDocument:
    retained_doc = tomlkit.document()
    overlay_preserved_tables(source_doc, retained_doc, retained_table_regexes)
    overlay_preserved_keys(source_doc, retained_doc, retained_key_paths)
    return normalize_document(retained_doc)


def merge_overlay_document(overlay_doc: TomlContainer, base_doc: TomlContainer) -> None:
    for key, overlay_value in overlay_doc.items():
        key_name = str(key)
        base_value = base_doc.get(key_name)

        if isinstance(overlay_value, Table) and isinstance(base_value, Table):
            merge_overlay_document(overlay_value, base_value)
            continue

        base_doc[key_name] = copy.deepcopy(overlay_value)


def merge_keys(
    base_path: Path,
    output_path: Path,
    overlay_path: Path,
    retained_key_paths: Iterable[tuple[str, ...]],
    retained_table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
 ) -> None:
    base_doc = load_document(base_path)
    merged_doc = copy.deepcopy(base_doc)
    if overlay_path.exists():
        overlay_doc = load_document(overlay_path)
        overlay_preserved_tables(overlay_doc, merged_doc, retained_table_regexes)
        overlay_preserved_keys(overlay_doc, merged_doc, retained_key_paths)
    write_document_if_changed(
        output_path,
        merged_doc,
        mode_reference_path=base_path,
        compare_path=compare_path,
    )


def merge_keys_except_stripped(
    base_path: Path,
    output_path: Path,
    overlay_path: Path,
    stripped_key_paths: list[tuple[str, ...]],
    stripped_table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
 ) -> None:
    base_doc = load_document(base_path)
    merged_doc = copy.deepcopy(base_doc)
    if overlay_path.exists():
        overlay_doc = load_document(overlay_path)
        filtered_overlay_doc = build_document_with_stripped_matchers(
            overlay_doc,
            stripped_key_paths,
            stripped_table_regexes,
        )
        merge_overlay_document(filtered_overlay_doc, merged_doc)
    write_document_if_changed(
        output_path,
        merged_doc,
        mode_reference_path=base_path,
        compare_path=compare_path,
    )


class TomlTransformEngine(BaseTransformEngine):
    name = "toml"
    SELECTOR_SPECS = (
        SelectorSpec(
            name="key",
            prefix="exact",
            is_default=True,
            description="exact TOML key path",
            examples=("model", "mcp_servers.playwright.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN"),
        ),
        SelectorSpec(
            name="table_regex",
            prefix="re",
            description="regex matching dotted TOML table paths",
            examples=(r"^projects\.", r"^mcp_servers\.playwright\.env$"),
        ),
    )

    def configure_parser(self, parser) -> None:
        parser.add_argument(
            "--compare-file",
            type=Path,
            help="Optional TOML file to compare against for exact no-op text reuse.",
        )

    def build_engine_options(self, parsed_args) -> dict[str, Any]:
        return {
            "compare_path": parsed_args.compare_file,
        }

    def validate_request(self, request: TransformRequest) -> None:
        super().validate_request(request)
        parse_key_paths(request.selector_values("key"))
        compile_table_regexes(request.selector_values("table_regex"))

    def transform(self, request: TransformRequest) -> None:
        self.validate_request(request)
        key_paths = parse_key_paths(request.selector_values("key"))
        table_regexes = compile_table_regexes(request.selector_values("table_regex"))
        compare_path = request.engine_option("compare_path")

        if request.mode == TransformMode.CLEANUP:
            if request.selector_action == SelectorAction.REMOVE:
                strip_keys(
                    request.base_path,
                    request.output_path,
                    key_paths,
                    table_regexes,
                    compare_path=compare_path,
                )
            else:
                retained_doc = build_document_with_retained_matchers(
                    load_document(request.base_path),
                    key_paths,
                    table_regexes,
                )
                write_document_if_changed(
                    request.output_path,
                    retained_doc,
                    mode_reference_path=request.base_path,
                    compare_path=compare_path,
                )
            return

        assert request.overlay_path is not None
        if request.selector_action == SelectorAction.REMOVE:
            merge_keys_except_stripped(
                request.base_path,
                request.output_path,
                request.overlay_path,
                key_paths,
                table_regexes,
                compare_path=compare_path,
            )
            return

        merge_keys(
            request.base_path,
            request.output_path,
            request.overlay_path,
            key_paths,
            table_regexes,
            compare_path=compare_path,
        )


def main(argv: list[str] | None = None) -> int:
    return run_engine_cli(TomlTransformEngine(), argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

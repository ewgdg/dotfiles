#!/usr/bin/env python3

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
from collections.abc import Iterable
from pathlib import Path
import tomlkit
from tomlkit.items import Null, Table
from tomlkit.toml_document import TOMLDocument

from scripts.transform_cli import run_engine_cli
from scripts.transform_engine import (
    BaseTransformEngine,
    SelectorAction,
    SelectorSpec,
    TransformMode,
    TransformOutput,
    TransformRequest,
    emit_transform_output,
)


TomlContainer = TOMLDocument | Table


@dataclass(frozen=True)
class TopLevelBodyRegion:
    key_name: str
    key: object
    item: object
    leading_entries: tuple[tuple[None, object], ...]


def load_document(path: Path) -> TOMLDocument:
    if not path.exists():
        return tomlkit.document()
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def get_existing_text_if_unchanged(compare_path: Path, doc: TOMLDocument) -> str | None:
    if not compare_path.exists():
        return None

    existing_content = compare_path.read_text(encoding="utf-8")
    try:
        existing_doc = tomlkit.parse(existing_content)
    except Exception:
        existing_doc = None

    if existing_doc is not None and existing_doc.unwrap() == doc.unwrap():
        return existing_content

    if existing_content != doc.as_string():
        return None

    return existing_content


def build_document_output(
    doc: TOMLDocument,
    *,
    mode_reference_path: Path,
    compare_path: Path | None = None,
) -> TransformOutput:
    content = doc.as_string()
    if compare_path is not None:
        existing_content = get_existing_text_if_unchanged(compare_path, doc)
        if existing_content is not None:
            return TransformOutput(
                content=existing_content,
                mode_reference_path=mode_reference_path,
                reused_compare_path=compare_path,
            )

    return TransformOutput(
        content=content,
        mode_reference_path=mode_reference_path,
    )



def write_document_if_changed(
    path: Path | None,
    doc: TOMLDocument,
    mode_reference_path: Path,
    compare_path: Path | None = None,
    stdout: bool = False,
) -> None:
    emit_transform_output(
        path,
        build_document_output(
            doc,
            mode_reference_path=mode_reference_path,
            compare_path=compare_path,
        ),
        stdout=stdout,
    )


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


def collect_top_level_body_regions(
    source_doc: TOMLDocument,
) -> tuple[dict[str, TopLevelBodyRegion], tuple[tuple[None, object], ...]]:
    regions: dict[str, TopLevelBodyRegion] = {}
    pending_leading_entries: list[tuple[None, object]] = []

    for key, item in source_doc._body:
        if key is None:
            if isinstance(item, Null):
                continue
            pending_leading_entries.append((None, copy.deepcopy(item)))
            continue

        if isinstance(item, Null):
            continue

        key_name = key.key
        regions[key_name] = TopLevelBodyRegion(
            key_name=key_name,
            key=copy.deepcopy(key),
            item=copy.deepcopy(item),
            leading_entries=tuple(pending_leading_entries),
        )
        pending_leading_entries = []

    return regions, tuple(pending_leading_entries)


def restore_top_level_leading_trivia(
    merged_doc: TOMLDocument,
    overlay_doc: TOMLDocument,
    base_doc: TOMLDocument,
    preserved_base: TOMLDocument,
) -> TOMLDocument:
    merged_regions, _merged_trailing_entries = collect_top_level_body_regions(merged_doc)
    overlay_regions, overlay_trailing_entries = collect_top_level_body_regions(overlay_doc)
    base_regions, base_trailing_entries = collect_top_level_body_regions(base_doc)
    preserved_regions, _preserved_trailing_entries = collect_top_level_body_regions(preserved_base)

    rebuilt_doc = tomlkit.document()

    for merged_region in merged_regions.values():
        overlay_region = overlay_regions.get(merged_region.key_name)
        base_region = base_regions.get(merged_region.key_name)
        preserved_region = preserved_regions.get(merged_region.key_name)

        if overlay_region is not None:
            leading_entries = overlay_region.leading_entries
        elif base_region is not None:
            leading_entries = base_region.leading_entries
        elif preserved_region is not None:
            leading_entries = preserved_region.leading_entries
        else:
            leading_entries = ()

        if (
            overlay_region is not None
            and preserved_region is not None
            and isinstance(overlay_region.item, Table)
            and isinstance(preserved_region.item, Table)
        ):
            item_region = merged_region
        elif overlay_region is not None:
            item_region = overlay_region
        elif base_region is not None:
            item_region = base_region
        else:
            item_region = merged_region

        # tomlkit stores standalone comments/blank lines outside keyed items.
        # Reattach the source-side leading trivia block to the following top-level
        # region so merge does not silently discard intentional commented config.
        for _unused_key, entry in leading_entries:
            rebuilt_doc.add(copy.deepcopy(entry))
        rebuilt_doc.append(copy.deepcopy(item_region.key), copy.deepcopy(item_region.item))

    trailing_entries: tuple[tuple[None, object], ...] = overlay_trailing_entries or base_trailing_entries
    for _unused_key, entry in trailing_entries:
        rebuilt_doc.add(copy.deepcopy(entry))

    return rebuilt_doc


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


def build_stripped_document_output(
    base_path: Path,
    stripped_key_paths: list[tuple[str, ...]],
    stripped_table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
) -> TransformOutput:
    normalized_doc = build_document_with_stripped_matchers(
        load_document(base_path),
        stripped_key_paths,
        stripped_table_regexes,
    )
    return build_document_output(
        normalized_doc,
        mode_reference_path=base_path,
        compare_path=compare_path,
    )



def strip_keys(
    base_path: Path,
    output_path: Path | None,
    stripped_key_paths: list[tuple[str, ...]],
    stripped_table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
    stdout: bool = False,
 ) -> None:
    emit_transform_output(
        output_path,
        build_stripped_document_output(
            base_path,
            stripped_key_paths,
            stripped_table_regexes,
            compare_path=compare_path,
        ),
        stdout=stdout,
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


def build_document_with_selector_action(
    source_doc: TOMLDocument,
    selector_action: SelectorAction,
    key_paths: list[tuple[str, ...]],
    table_regexes: list[re.Pattern[str]],
) -> TOMLDocument:
    if selector_action == SelectorAction.REMOVE:
        return build_document_with_stripped_matchers(
            source_doc,
            key_paths,
            table_regexes,
        )
    return build_document_with_retained_matchers(
        source_doc,
        key_paths,
        table_regexes,
    )


def clone_empty_container(source: TomlContainer) -> TomlContainer:
    cloned = copy.deepcopy(source)
    for key in list(cloned.keys()):
        del cloned[key]
    return cloned


def overlay_with_base_slots(
    original_base: TomlContainer,
    preserved_base: TomlContainer,
    overlay_doc: TomlContainer,
) -> TomlContainer:
    merged = clone_empty_container(preserved_base)

    for key in original_base.keys():
        key_name = str(key)
        base_value = original_base.get(key_name)
        preserved_value = preserved_base.get(key_name)
        overlay_value = overlay_doc.get(key_name)

        if (
            isinstance(base_value, Table)
            and isinstance(preserved_value, Table)
            and isinstance(overlay_value, Table)
        ):
            merged[key_name] = overlay_with_base_slots(base_value, preserved_value, overlay_value)
            continue

        if overlay_value is not None:
            merged[key_name] = copy.deepcopy(overlay_value)
            continue

        if preserved_value is not None:
            merged[key_name] = copy.deepcopy(preserved_value)

    for key, overlay_value in overlay_doc.items():
        key_name = str(key)
        if key_name in merged:
            continue
        merged[key_name] = copy.deepcopy(overlay_value)

    for key, preserved_value in preserved_base.items():
        key_name = str(key)
        if key_name in merged:
            continue
        merged[key_name] = copy.deepcopy(preserved_value)

    return merged


def build_merged_document_output(
    base_path: Path,
    overlay_path: Path,
    selector_action: SelectorAction,
    key_paths: list[tuple[str, ...]],
    table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
) -> TransformOutput:
    base_doc = load_document(base_path)
    preserved_base = build_document_with_selector_action(
        base_doc,
        selector_action,
        key_paths,
        table_regexes,
    )
    overlay_doc = load_document(overlay_path)
    merged_doc = normalize_document(overlay_with_base_slots(base_doc, preserved_base, overlay_doc))
    merged_doc = restore_top_level_leading_trivia(merged_doc, overlay_doc, base_doc, preserved_base)
    return build_document_output(
        merged_doc,
        mode_reference_path=base_path,
        compare_path=compare_path,
    )



def merge_with_selector_action(
    base_path: Path,
    output_path: Path | None,
    overlay_path: Path,
    selector_action: SelectorAction,
    key_paths: list[tuple[str, ...]],
    table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
    stdout: bool = False,
) -> None:
    emit_transform_output(
        output_path,
        build_merged_document_output(
            base_path,
            overlay_path,
            selector_action,
            key_paths,
            table_regexes,
            compare_path=compare_path,
        ),
        stdout=stdout,
    )


def merge_keys(
    base_path: Path,
    output_path: Path | None,
    overlay_path: Path,
    retained_key_paths: Iterable[tuple[str, ...]],
    retained_table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
    stdout: bool = False,
) -> None:
    merge_with_selector_action(
        base_path,
        output_path,
        overlay_path,
        SelectorAction.RETAIN,
        list(retained_key_paths),
        retained_table_regexes,
        compare_path=compare_path,
        stdout=stdout,
    )


def merge_keys_except_stripped(
    base_path: Path,
    output_path: Path | None,
    overlay_path: Path,
    stripped_key_paths: list[tuple[str, ...]],
    stripped_table_regexes: list[re.Pattern[str]],
    compare_path: Path | None = None,
    stdout: bool = False,
 ) -> None:
    merge_with_selector_action(
        base_path,
        output_path,
        overlay_path,
        SelectorAction.REMOVE,
        stripped_key_paths,
        stripped_table_regexes,
        compare_path=compare_path,
        stdout=stdout,
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
            "stdout": parsed_args.stdout,
        }

    def validate_request(self, request: TransformRequest) -> None:
        super().validate_request(request)
        parse_key_paths(request.selector_values("key"))
        compile_table_regexes(request.selector_values("table_regex"))

    def transform(self, request: TransformRequest) -> TransformOutput:
        self.validate_request(request)
        key_paths = parse_key_paths(request.selector_values("key"))
        table_regexes = compile_table_regexes(request.selector_values("table_regex"))
        compare_path = request.engine_option("compare_path")

        if request.mode == TransformMode.CLEANUP:
            if request.selector_action == SelectorAction.REMOVE:
                return build_stripped_document_output(
                    request.base_path,
                    key_paths,
                    table_regexes,
                    compare_path=compare_path,
                )

            filtered_doc = build_document_with_selector_action(
                load_document(request.base_path),
                request.selector_action,
                key_paths,
                table_regexes,
            )
            return build_document_output(
                filtered_doc,
                mode_reference_path=request.base_path,
                compare_path=compare_path,
            )

        assert request.overlay_path is not None
        return build_merged_document_output(
            request.base_path,
            request.overlay_path,
            request.selector_action,
            key_paths,
            table_regexes,
            compare_path=compare_path,
        )


def main(argv: list[str] | None = None) -> int:
    return run_engine_cli(TomlTransformEngine(), argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

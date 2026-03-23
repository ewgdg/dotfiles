#!/usr/bin/env python3

from __future__ import annotations

import copy
import fnmatch
from pathlib import Path
import sys
import xml.dom.minidom
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.transform_cli import run_engine_cli  # noqa: E402
from scripts.transform_engine import (  # noqa: E402
    BaseTransformEngine,
    SelectorAction,
    SelectorSpec,
    TransformRequest,
)


def sync_mode(reference_path: Path, output_path: Path) -> None:
    if not reference_path.is_file() or not output_path.exists():
        return

    target_mode = reference_path.stat().st_mode & 0o777
    current_mode = output_path.stat().st_mode & 0o777
    if current_mode != target_mode:
        output_path.chmod(target_mode)


def matches_node_path(node_path: str, node_matchers: list[str]) -> bool:
    return any(fnmatch.fnmatch(node_path, node_matcher) for node_matcher in node_matchers)


def overlay_retained_nodes(
    base_root: ET.Element,
    overlay_root: ET.Element,
    node_matchers: list[str] | None = None,
) -> None:
    def element_identity_key(element: ET.Element) -> tuple[tuple[str, str], ...] | None:
        identity_parts: list[tuple[str, str]] = []
        for attribute_name in ("id", "name", "key", "uuid"):
            attribute_value = element.attrib.get(attribute_name)
            if attribute_value is not None:
                identity_parts.append((attribute_name, attribute_value))

        text_value = (element.text or "").strip()
        if text_value:
            identity_parts.append(("text", text_value))

        if not identity_parts:
            return None

        return tuple(identity_parts)

    def overlay_retained_nodes_recursion(
        base_node: ET.Element,
        overlay_node: ET.Element,
        cur_path: str,
        node_matchers: list[str] | None = None,
    ) -> None:
        original_base_children = list(base_node)
        children_by_tag: dict[str, list[tuple[int, ET.Element]]] = {}
        children_by_identity: dict[
            tuple[str, tuple[tuple[str, str], ...]], list[tuple[int, ET.Element]]
        ] = {}

        for index, child in enumerate(original_base_children):
            children_by_tag.setdefault(child.tag, []).append((index, child))
            identity_key = element_identity_key(child)
            if identity_key is not None:
                children_by_identity.setdefault((child.tag, identity_key), []).append(
                    (index, child)
                )

        used_indices: set[int] = set()
        merged_children: list[ET.Element] = []

        def find_matching_child(
            target: ET.Element,
        ) -> tuple[int, ET.Element] | None:
            identity_key = element_identity_key(target)
            if identity_key is not None:
                for index, child in children_by_identity.get(
                    (target.tag, identity_key), []
                ):
                    if index not in used_indices:
                        return (index, child)
                return None

            for index, child in children_by_tag.get(target.tag, []):
                if index not in used_indices:
                    return (index, child)

            return None

        for overlay_child in overlay_node:
            child_path = f"{cur_path}/{overlay_child.tag}"
            match = find_matching_child(overlay_child)
            should_overlay = False
            if node_matchers:
                should_overlay = matches_node_path(child_path, node_matchers)
            else:
                should_overlay = len(overlay_child) == 0 or match is None

            if match is not None:
                base_child_index, base_child = match
                used_indices.add(base_child_index)
                if should_overlay:
                    merged_children.append(copy.deepcopy(overlay_child))
                else:
                    overlay_retained_nodes_recursion(
                        base_child,
                        overlay_child,
                        child_path,
                        node_matchers,
                    )
                    merged_children.append(base_child)
            elif should_overlay:
                merged_children.append(copy.deepcopy(overlay_child))

        for index, child in enumerate(original_base_children):
            if index in used_indices:
                continue
            merged_children.append(child)

        base_node[:] = merged_children

    overlay_retained_nodes_recursion(base_root, overlay_root, base_root.tag, node_matchers)


def build_tree_with_retained_nodes(
    source_root: ET.Element,
    node_matchers: list[str],
) -> ET.Element:
    def build_retained_subtree(current: ET.Element, cur_path: str) -> ET.Element | None:
        if matches_node_path(cur_path, node_matchers):
            return copy.deepcopy(current)

        retained_children: list[ET.Element] = []
        for child in current:
            child_path = f"{cur_path}/{child.tag}"
            retained_child = build_retained_subtree(child, child_path)
            if retained_child is not None:
                retained_children.append(retained_child)

        retained_current = ET.Element(current.tag, dict(current.attrib))
        retained_current.text = current.text
        retained_current.tail = current.tail
        retained_current.extend(retained_children)
        if retained_children or cur_path == source_root.tag:
            return retained_current
        return None

    retained_root = build_retained_subtree(source_root, source_root.tag)
    if retained_root is None:
        return ET.Element(source_root.tag, dict(source_root.attrib))
    return retained_root


def strip_nodes(root: ET.Element, node_matchers: list[str]) -> None:
    def strip_nodes_recursion(
        current: ET.Element,
        parent: ET.Element | None,
        cur_path: str,
        node_matchers: list[str],
    ) -> None:
        for node_matcher in node_matchers:
            if fnmatch.fnmatch(cur_path, node_matcher):
                if parent is not None:
                    parent.remove(current)
                else:
                    current.clear()
                return

        for child in list(current):
            child_path = f"{cur_path}/{child.tag}"
            strip_nodes_recursion(child, current, child_path, node_matchers)

    strip_nodes_recursion(root, None, root.tag, node_matchers)


def build_tree_with_stripped_nodes(
    source_root: ET.Element,
    node_matchers: list[str],
) -> ET.Element:
    stripped_root = copy.deepcopy(source_root)
    strip_nodes(stripped_root, node_matchers)
    return stripped_root


def parse_node_matchers(raw_node_matchers: tuple[str, ...]) -> list[str]:
    parsed_node_matchers: list[str] = []
    for raw_matcher_group in raw_node_matchers:
        for raw_matcher in raw_matcher_group.split(","):
            node_matcher = raw_matcher.strip()
            if node_matcher:
                parsed_node_matchers.append(node_matcher)
    return parsed_node_matchers


def sort_xml_attributes(root: ET.Element) -> None:
    for elem in root.iter():
        sorted_attributes = dict(sorted(elem.attrib.items()))
        elem.attrib.clear()
        elem.attrib.update(sorted_attributes)


def strip_whitespace_text_nodes(root: ET.Element) -> None:
    for elem in root.iter():
        if elem.text is not None and elem.text.strip() == "":
            elem.text = None
        if elem.tail is not None and elem.tail.strip() == "":
            elem.tail = None


def normalized_xml_for_compare(root: ET.Element) -> str:
    normalized = copy.deepcopy(root)
    strip_whitespace_text_nodes(normalized)
    sort_xml_attributes(normalized)
    return ET.tostring(normalized, encoding="unicode")


def get_existing_xml_bytes_if_semantically_unchanged(
    compare_path: Path,
    root: ET.Element,
 ) -> bytes | None:
    if not compare_path.is_file():
        return None

    existing_bytes = compare_path.read_bytes()
    try:
        existing_root = ET.fromstring(existing_bytes)
    except ET.ParseError:
        return None

    if normalized_xml_for_compare(existing_root) != normalized_xml_for_compare(root):
        return None

    return existing_bytes


def write_output_bytes(
    output_path: Path,
    content: bytes,
    mode_reference_path: Path,
 ) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    sync_mode(mode_reference_path, output_path)


def transform_xml(
    base_path: str | Path,
    output_path: str | Path,
    node_matchers: list[str] | None = None,
    sort_attributes: bool = False,
    overlay_path: str | Path | None = None,
    selector_action: SelectorAction | None = None,
    compare_path: str | Path | None = None,
 ) -> None:
    base_path = Path(base_path)
    output_path = Path(output_path)
    overlay_path = Path(overlay_path) if overlay_path is not None else None
    compare_path = Path(compare_path) if compare_path is not None else None
    effective_selector_action = (
        selector_action
        if selector_action is not None
        else SelectorAction.RETAIN
        if overlay_path is not None
        else SelectorAction.REMOVE
    )
    parsed_node_matchers = node_matchers or []

    tree = None
    overlay_root = None
    if base_path.is_file():
        tree = ET.parse(base_path)

    if overlay_path is not None and overlay_path.is_file():
        overlay_tree = ET.parse(overlay_path)
        overlay_root = overlay_tree.getroot()
        if tree is None:
            root = ET.Element(overlay_root.tag)
            tree = ET.ElementTree(root)
        else:
            root = tree.getroot()

        filtered_overlay_root = (
            build_tree_with_retained_nodes(overlay_root, parsed_node_matchers)
            if effective_selector_action == SelectorAction.RETAIN
            else build_tree_with_stripped_nodes(overlay_root, parsed_node_matchers)
        )
        if effective_selector_action == SelectorAction.RETAIN:
            overlay_retained_nodes(root, overlay_root, parsed_node_matchers)
        else:
            overlay_retained_nodes(root, filtered_overlay_root)

    if tree is None:
        raise FileNotFoundError(f"File not found: {base_path}")

    root = tree.getroot()
    if root is None:
        raise ValueError("Root element not found in the XML file.")

    if parsed_node_matchers and overlay_path is None:
        if effective_selector_action == SelectorAction.RETAIN:
            retained_root = build_tree_with_retained_nodes(root, parsed_node_matchers)
            root.clear()
            root.attrib.update(retained_root.attrib)
            root.text = retained_root.text
            root.tail = retained_root.tail
            root.extend(list(retained_root))
        else:
            strip_nodes(root, parsed_node_matchers)

    if sort_attributes:
        sort_xml_attributes(root)

    if compare_path is not None:
        existing_bytes = get_existing_xml_bytes_if_semantically_unchanged(compare_path, root)
        if existing_bytes is not None:
            write_output_bytes(output_path, existing_bytes, base_path)
            return

    xml_string = ET.tostring(root, encoding="unicode")
    dom = xml.dom.minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent="  ", newl="\n")
    lines = pretty_xml.splitlines()
    pretty_xml = "\n".join(
        line
        for line in lines
        if len(line.strip()) > 0
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(pretty_xml, encoding="utf-8")
    sync_mode(base_path, output_path)


class XmlTransformEngine(BaseTransformEngine):
    name = "xml"
    SELECTOR_SPECS = (
        SelectorSpec(
            name="node_matcher",
            prefix="exact",
            is_default=True,
            description="fnmatch-style XML node path matcher",
            examples=("config/WindowGeometry", "config/*WindowState"),
        ),
    )

    def configure_parser(self, parser) -> None:
        parser.add_argument(
            "--compare-file",
            type=Path,
            help="Optional XML file to compare against for semantic no-op byte reuse.",
        )
        parser.add_argument(
            "--sort-attributes",
            action="store_true",
            dest="sort_attributes",
            help="Sort attributes of each element alphabetically.",
        )

    def build_engine_options(self, parsed_args) -> dict[str, object]:
        return {
            "compare_path": parsed_args.compare_file,
            "sort_attributes": parsed_args.sort_attributes,
        }

    def validate_request(self, request: TransformRequest) -> None:
        super().validate_request(request)
        if not parse_node_matchers(request.selector_values("node_matcher")):
            raise ValueError("node matchers must not be empty")

    def transform(self, request: TransformRequest) -> None:
        self.validate_request(request)
        transform_xml(
            request.base_path,
            request.output_path,
            node_matchers=parse_node_matchers(request.selector_values("node_matcher")),
            sort_attributes=bool(request.engine_option("sort_attributes", False)),
            overlay_path=request.overlay_path,
            selector_action=request.selector_action,
            compare_path=request.engine_option("compare_path"),
        )

def main(argv: list[str] | None = None) -> int:
    return run_engine_cli(XmlTransformEngine(), argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

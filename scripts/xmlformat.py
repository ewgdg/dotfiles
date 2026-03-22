import argparse
import copy
import fnmatch
import os
import xml.dom.minidom
import xml.etree.ElementTree as ET


def sync_mode(reference_file: str, output_file: str) -> None:
    if not os.path.isfile(reference_file) or not os.path.exists(output_file):
        return

    target_mode = os.stat(reference_file).st_mode & 0o777
    current_mode = os.stat(output_file).st_mode & 0o777
    if current_mode != target_mode:
        os.chmod(output_file, target_mode)


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
        children_by_tag: dict[str, list[tuple[int, ET.Element]]] = {}
        children_by_identity: dict[
            tuple[str, tuple[tuple[str, str], ...]], list[tuple[int, ET.Element]]
        ] = {}

        for index, child in enumerate(list(base_node)):
            children_by_tag.setdefault(child.tag, []).append((index, child))
            identity_key = element_identity_key(child)
            if identity_key is not None:
                children_by_identity.setdefault((child.tag, identity_key), []).append(
                    (index, child)
                )

        used_indices: set[int] = set()

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
                for node_matcher in node_matchers:
                    if fnmatch.fnmatch(child_path, node_matcher):
                        should_overlay = True
                        break
            elif len(overlay_child) == 0 or match is None:
                should_overlay = True

            if match is not None:
                base_child_index, base_child = match
                used_indices.add(base_child_index)
                if should_overlay:
                    base_node[base_child_index] = copy.deepcopy(overlay_child)
                else:
                    overlay_retained_nodes_recursion(
                        base_child,
                        overlay_child,
                        child_path,
                        node_matchers,
                    )
            elif should_overlay:
                base_node.append(copy.deepcopy(overlay_child))
                appended_index = len(base_node) - 1
                used_indices.add(appended_index)
                children_by_tag.setdefault(overlay_child.tag, []).append(
                    (appended_index, base_node[appended_index])
                )
                appended_identity_key = element_identity_key(overlay_child)
                if appended_identity_key is not None:
                    children_by_identity.setdefault(
                        (overlay_child.tag, appended_identity_key), []
                    ).append((appended_index, base_node[appended_index]))

    overlay_retained_nodes_recursion(base_root, overlay_root, base_root.tag, node_matchers)


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


def sort_attributes(root: ET.Element):
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
    sort_attributes(normalized)
    return ET.tostring(normalized, encoding="unicode")


def process_xml(
    base_file: str,
    output_file: str,
    node_matchers: list[str] | None = None,
    sort_attrs=False,
    overlay_file: str | None = None,
    write_base_unchanged_if_no_effect=False,
) -> None:
    tree = None
    base_bytes = None
    before_root = None
    if os.path.isfile(base_file):
        with open(base_file, "rb") as f:
            base_bytes = f.read()
        tree = ET.parse(base_file)
        before_root = copy.deepcopy(tree.getroot())

    if overlay_file and os.path.isfile(overlay_file):
        overlay_tree = ET.parse(overlay_file)
        overlay_root = overlay_tree.getroot()
        if tree is None:
            root = ET.Element(overlay_root.tag)
            tree = ET.ElementTree(root)
        else:
            root = tree.getroot()

        overlay_retained_nodes(root, overlay_root, node_matchers)

    if tree is None:
        raise FileNotFoundError(f"File not found: {base_file}")

    root = tree.getroot()

    if root is None:
        raise ValueError("Root element not found in the XML file.")

    if node_matchers and overlay_file is None:
        strip_nodes(root, node_matchers)

    if sort_attrs:
        sort_attributes(root)

    if (
        write_base_unchanged_if_no_effect
        and before_root is not None
        and base_bytes is not None
        and normalized_xml_for_compare(before_root) == normalized_xml_for_compare(root)
    ):
        with open(output_file, "wb") as output:
            output.write(base_bytes)
        sync_mode(base_file, output_file)
        return

    # Convert ElementTree object to a string
    xml_string = ET.tostring(root, encoding="unicode")
    # Parse the string using minidom for pretty-printing
    dom = xml.dom.minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent="  ", newl="\n")
    lines = pretty_xml.splitlines()
    pretty_xml = "\n".join(
        line
        for line in lines
        if len(line.strip()) > 0  # and not line.startswith("<?xml")
    )

    # Write the formatted XML to a file
    with open(output_file, "w") as output:
        output.write(pretty_xml)
    sync_mode(base_file, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Strip selected nodes from a base XML file, or retain selected nodes from "
            "an overlay XML file on top of a base XML file."
        )
    )
    parser.add_argument("base_file", help="Base XML file. Repo file for install mode.")
    parser.add_argument("output_file", help="The path to the output XML file.")
    parser.add_argument(
        "--node-matchers",
        "--node-paths",
        "--strip-nodes",
        "--retain-nodes",
        "--remove_nodes",
        "--merge_nodes",
        dest="node_matchers",
        help=(
            "Comma-separated list of XML node matchers. Without --overlay-file they "
            "are stripped from the base file; with --overlay-file they are retained "
            "from the overlay file."
        ),
    )
    parser.add_argument(
        "--sort_attributes",
        action="store_true",
        help="Sort attributes of each element alphabetically.",
    )

    parser.add_argument(
        "--overlay-file",
        "--merge_file",
        dest="overlay_file",
        help="Overlay XML file. Live file for install mode.",
    )

    parser.add_argument(
        "--write-base-unchanged-if-no-effect",
        "--write_input_unchanged_if_no_effect",
        dest="write_base_unchanged_if_no_effect",
        action="store_true",
        help="If changes are semantically a no-op, write the original base bytes to output.",
    )

    args = parser.parse_args()

    process_xml(
        args.base_file,
        args.output_file,
        node_matchers=args.node_matchers.split(",")
        if args.node_matchers is not None and args.node_matchers != ""
        else None,
        sort_attrs=args.sort_attributes,
        overlay_file=args.overlay_file,
        write_base_unchanged_if_no_effect=args.write_base_unchanged_if_no_effect,
    )

import os
import xml.etree.ElementTree as ET
import fnmatch
import argparse
import xml.dom.minidom
import copy


def sync_mode(reference_file: str, output_file: str) -> None:
    if not os.path.isfile(reference_file) or not os.path.exists(output_file):
        return

    target_mode = os.stat(reference_file).st_mode & 0o777
    current_mode = os.stat(output_file).st_mode & 0o777
    if current_mode != target_mode:
        os.chmod(output_file, target_mode)


def merge_nodes(
    layer1: ET.Element, layer2: ET.Element, paths_to_merge: list[str] | None = None
):
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

    def merge_nodes_recursion(
        layer1: ET.Element,
        layer2: ET.Element,
        cur_path: str,
        paths_to_merge: list[str] | None = None,
    ):
        children_by_tag: dict[str, list[tuple[int, ET.Element]]] = {}
        children_by_identity: dict[
            tuple[str, tuple[tuple[str, str], ...]], list[tuple[int, ET.Element]]
        ] = {}

        for index, child in enumerate(list(layer1)):
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

        for layer2_child in layer2:
            child_path = f"{cur_path}/{layer2_child.tag}"
            match = find_matching_child(layer2_child)
            should_merge = False
            if paths_to_merge:
                for path_to_merge in paths_to_merge:
                    if fnmatch.fnmatch(child_path, path_to_merge):
                        should_merge = True
            elif len(layer2_child) == 0 or match is None:
                should_merge = True

            if match is not None:
                layer1_child_i, layer1_child = match
                used_indices.add(layer1_child_i)
                if should_merge:
                    # print(f"Merging element {child_path} to index {layer1_child_i}")
                    layer1[layer1_child_i] = layer2_child
                else:
                    merge_nodes_recursion(
                        layer1_child,
                        layer2_child,
                        child_path,
                        paths_to_merge,
                    )
            elif should_merge:
                # Add new child node if not present
                # print(f"Adding new element: {child_path}")
                layer1.append(layer2_child)
                appended_index = len(layer1) - 1
                used_indices.add(appended_index)
                children_by_tag.setdefault(layer2_child.tag, []).append(
                    (appended_index, layer2_child)
                )
                appended_identity_key = element_identity_key(layer2_child)
                if appended_identity_key is not None:
                    children_by_identity.setdefault(
                        (layer2_child.tag, appended_identity_key), []
                    ).append((appended_index, layer2_child))

    merge_nodes_recursion(layer1, layer2, layer1.tag, paths_to_merge)


def remove_nodes(cur: ET.Element, paths_to_remove: list):
    def remove_nodes_recursion(
        cur: ET.Element,
        parent: ET.Element | None,
        cur_path: str,
        paths_to_remove: list[str],
    ):
        # print(f"Current, {cur.tag},  path: {cur_path}")
        for path_to_remove in paths_to_remove:
            # Check if the current path matches the pattern to ignore
            if fnmatch.fnmatch(cur_path, path_to_remove):
                # print(f"Removing element: {cur_path}")
                if parent is not None:
                    parent.remove(cur)
                else:
                    cur.clear()
                return

        for child in list(cur):  # make a copy of children to avoid runtime error
            child_path = f"{cur_path}/{child.tag}"
            # Recursively check child elements
            remove_nodes_recursion(child, cur, child_path, paths_to_remove)

    remove_nodes_recursion(cur, None, cur.tag, paths_to_remove)


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
    input_file,
    output_file,
    patterns_for_removal=None,
    sort_attrs=False,
    merge_file=None,
    patterns_for_merge=None,
    write_input_unchanged_if_no_effect=False,
):
    tree = None
    input_bytes = None
    before_root = None
    if os.path.isfile(input_file):
        with open(input_file, "rb") as f:
            input_bytes = f.read()
        tree = ET.parse(input_file)
        before_root = copy.deepcopy(tree.getroot())

    if merge_file and os.path.isfile(merge_file):
        merge_tree = ET.parse(merge_file)
        merge_root = merge_tree.getroot()
        if tree is None:
            root = ET.Element(merge_root.tag)
            tree = ET.ElementTree(root)
        else:
            root = tree.getroot()

        merge_nodes(root, merge_root, patterns_for_merge)

    if tree is None:
        raise FileNotFoundError(f"File not found: {input_file}")

    root = tree.getroot()

    if root is None:
        raise ValueError("Root element not found in the XML file.")

    if patterns_for_removal:
        remove_nodes(root, patterns_for_removal)

    if sort_attrs:
        sort_attributes(root)

    if (
        write_input_unchanged_if_no_effect
        and before_root is not None
        and input_bytes is not None
        and normalized_xml_for_compare(before_root) == normalized_xml_for_compare(root)
    ):
        with open(output_file, "wb") as output:
            output.write(input_bytes)
        sync_mode(input_file, output_file)
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
    sync_mode(input_file, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process and modify XML files.")
    parser.add_argument("input_file", help="The path to the input XML file.")
    parser.add_argument("output_file", help="The path to the output XML file.")
    parser.add_argument(
        "--remove_nodes",
        help="Comma-separated list of tag patterns to remove.",
    )
    parser.add_argument(
        "--sort_attributes",
        action="store_true",
        help="Sort attributes of each element alphabetically.",
    )

    parser.add_argument(
        "--merge_file",
        help="additionally merge the xml.",
    )

    parser.add_argument(
        "--merge_nodes",
        help="only merge the given nodes.",
    )

    parser.add_argument(
        "--write_input_unchanged_if_no_effect",
        action="store_true",
        help="If changes are semantically a no-op, write the original input bytes to output.",
    )

    args = parser.parse_args()

    process_xml(
        args.input_file,
        args.output_file,
        patterns_for_removal=args.remove_nodes.split(",")
        if args.remove_nodes is not None and args.remove_nodes != ""
        else None,
        sort_attrs=args.sort_attributes,
        merge_file=args.merge_file,
        patterns_for_merge=args.merge_nodes.split(",")
        if args.merge_nodes is not None and args.merge_nodes != ""
        else None,
        write_input_unchanged_if_no_effect=args.write_input_unchanged_if_no_effect,
    )

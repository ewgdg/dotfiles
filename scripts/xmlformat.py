import os
import xml.etree.ElementTree as ET
import fnmatch
import argparse
import xml.dom.minidom


def merge_nodes(
    layer1: ET.Element, layer2: ET.Element, paths_to_merge: list[str] | None = None
):
    def merge_nodes_recursion(
        layer1: ET.Element,
        layer2: ET.Element,
        cur_path: str,
        paths_to_merge: list[str] | None = None,
    ):
        layer1_child_map = {child.tag: (child, i) for i, child in enumerate(layer1)}
        for layer2_child in layer2:
            child_path = f"{cur_path}/{layer2_child.tag}"
            should_merge = False
            if paths_to_merge:
                for path_to_merge in paths_to_merge:
                    if fnmatch.fnmatch(child_path, path_to_merge):
                        should_merge = True
            elif len(layer2_child) == 0 or layer2_child.tag not in layer1_child_map:
                should_merge = True

            if layer2_child.tag in layer1_child_map:
                layer1_child, layer1_child_i = layer1_child_map[layer2_child.tag]
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
                print(f"Removing element: {cur_path}")
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


def process_xml(
    input_file,
    output_file,
    patterns_for_removal=None,
    sort_attrs=False,
    merge_file=None,
    patterns_for_merge=None,
):
    tree = None
    if os.path.isfile(input_file):
        tree = ET.parse(input_file)

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
    )

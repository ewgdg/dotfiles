#!/usr/bin/env python3
"""Render and capture GoldenDict config with a templated dictionary path."""

from __future__ import annotations

import argparse
import contextlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.dom.minidom
import xml.etree.ElementTree as ET

from scripts.transform_engine import SelectorAction
from scripts.xml_transform import transform_xml


REPO_DICTIONARY_DIR_PLACEHOLDER = "{{ vars.goldendict.dictionary_dir }}"
_ENV_VAR_PATTERN = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\:-(.*?)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
)


def patch_xml_text(
    xml_text: str,
    *,
    dictionary_dir_template: str = REPO_DICTIONARY_DIR_PLACEHOLDER,
) -> str:
    root = ET.fromstring(xml_text)
    path_nodes = root.findall("./paths/path")
    if not path_nodes:
        raise ValueError("expected at least one config/paths/path node")

    path_values = {(node.text or "").strip() for node in path_nodes}
    if len(path_values) > 1:
        raise ValueError(
            "multiple distinct dictionary paths found under config/paths/path"
        )

    for path_node in path_nodes:
        path_node.text = dictionary_dir_template

    xml_string = ET.tostring(root, encoding="unicode")
    pretty_xml = xml.dom.minidom.parseString(xml_string).toprettyxml(
        indent="  ",
        newl="\n",
    )
    return "\n".join(line for line in pretty_xml.splitlines() if line.strip())


def cleanup_xml_text(
    base_path: Path,
    *,
    selectors: tuple[str, ...],
    sort_children: tuple[str, ...],
) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        transform_xml(
            base_path,
            None,
            node_matchers=list(selectors),
            sort_attributes=True,
            selector_action=SelectorAction.REMOVE,
            child_sort_parent_matchers=list(sort_children),
            stdout=True,
        )
    return output.getvalue()


def render_repo_template(repo_path: Path) -> str:
    result = subprocess.run(
        ["dotman", "render", "jinja", str(repo_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def expand_shell_path(path_value: str) -> str:
    def replace_match(match: re.Match[str]) -> str:
        fallback_var_name = match.group(1)
        fallback_value = match.group(2)
        simple_var_name = match.group(3)

        if simple_var_name is not None:
            return os.environ.get(simple_var_name, match.group(0))

        assert fallback_var_name is not None
        configured_value = os.environ.get(fallback_var_name)
        if configured_value:
            return configured_value
        assert fallback_value is not None
        return expand_shell_path(fallback_value)

    expanded_path = path_value
    while True:
        next_path = _ENV_VAR_PATTERN.sub(replace_match, expanded_path)
        if next_path == expanded_path:
            return os.path.expanduser(next_path)
        expanded_path = next_path


def render_repo_xml(repo_path: Path) -> str:
    rendered_repo_xml = render_repo_template(repo_path)
    root = ET.fromstring(rendered_repo_xml)
    for path_node in root.findall("./paths/path"):
        path_node.text = expand_shell_path((path_node.text or "").strip())
    return ET.tostring(root, encoding="unicode")


def merge_rendered_repo_xml(
    base_path: Path,
    *,
    rendered_repo_xml: str,
    selectors: tuple[str, ...],
    sort_children: tuple[str, ...],
) -> str:
    with tempfile.TemporaryDirectory(prefix="goldendict-render-") as temp_dir:
        overlay_path = Path(temp_dir) / "overlay.xml"
        overlay_path.write_text(rendered_repo_xml, encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            transform_xml(
                base_path,
                None,
                node_matchers=list(selectors),
                overlay_path=overlay_path,
                selector_action=SelectorAction.RETAIN,
                compare_path=base_path,
                child_sort_parent_matchers=list(sort_children),
                stdout=True,
            )
        return output.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render and capture GoldenDict config with a templated dictionary path."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("base_path", type=Path)
    capture_parser.add_argument("--selectors", nargs="+", required=True)
    capture_parser.add_argument("--sort-children", nargs="+", default=())

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("base_path", type=Path)
    render_parser.add_argument("repo_path", type=Path)
    render_parser.add_argument("--selectors", nargs="+", required=True)
    render_parser.add_argument("--sort-children", nargs="+", default=())

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "capture":
        sys.stdout.write(
            patch_xml_text(
                cleanup_xml_text(
                    args.base_path,
                    selectors=tuple(args.selectors),
                    sort_children=tuple(args.sort_children),
                )
            )
        )
        return 0

    if args.command == "render":
        sys.stdout.write(
            merge_rendered_repo_xml(
                args.base_path,
                rendered_repo_xml=render_repo_xml(args.repo_path),
                selectors=tuple(args.selectors),
                sort_children=tuple(args.sort_children),
            )
        )
        return 0

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

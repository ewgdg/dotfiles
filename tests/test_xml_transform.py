from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "xml_transform.py"


def load_module():
    spec = importlib.util.spec_from_file_location("xml_transform", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def parse_xml(path: Path) -> ET.Element:
    return ET.parse(path).getroot()

def write_semantically_equal_overlay_xml(repo_path: Path, live_path: Path) -> str:
    repo_path.write_text(
        """<config>
  <keep id=\"1\"></keep>
  <tail></tail>
</config>
""",
        encoding="utf-8",
    )
    live_text = """<?xml version=\"1.0\"?>
<config>
 <keep id=\"1\"/>
 <WindowGeometry y=\"200\" x=\"100\"/>
 <tail/>
</config>"""
    live_path.write_text(live_text, encoding="utf-8")
    return live_text


def test_xml_engine_declares_typed_selectors() -> None:
    selector_specs = {spec.name: spec for spec in MODULE.XmlTransformEngine.selector_specs()}

    assert (
        selector_specs["node_matcher"].option_name(MODULE.SelectorAction.RETAIN)
        == "--retain-node-matcher"
    )


def test_main_accepts_typed_selector_flags(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.xml"
    live_path = tmp_path / "live.xml"
    output_path = tmp_path / "output.xml"

    repo_path.write_text(
        """<config>
  <keep>repo</keep>
</config>
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """<config>
  <keep>live</keep>
  <WindowGeometry y="200" x="100" />
</config>
""",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(repo_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(live_path),
            "--retain-node-matcher",
            "config/WindowGeometry",
            "--sort-attributes",
        ]
    )

    assert exit_code == 0
    root = parse_xml(output_path)
    assert root.findtext("keep") == "repo"
    assert root.find("WindowGeometry") is not None
    assert root.find("WindowGeometry").attrib == {"x": "100", "y": "200"}


def test_parse_node_matchers_accepts_repeated_and_comma_separated_values() -> None:
    assert MODULE.parse_node_matchers(
        ("config/WindowGeometry,config/WindowState", "config/timeForNewReleaseCheck")
    ) == [
        "config/WindowGeometry",
        "config/WindowState",
        "config/timeForNewReleaseCheck",
    ]


def test_strip_nodes_removes_selected_live_only_xml_paths(tmp_path: Path) -> None:
    input_path = tmp_path / "input.xml"
    output_path = tmp_path / "output.xml"

    input_path.write_text(
        """<config>
  <WindowGeometry x="100" y="200" />
  <WindowState fullscreen="true" />
  <timeForNewReleaseCheck>12345</timeForNewReleaseCheck>
  <keep>repo</keep>
</config>
""",
        encoding="utf-8",
    )

    MODULE.transform_xml(
        str(input_path),
        str(output_path),
        node_matchers=[
            "config/WindowGeometry",
            "config/WindowState",
            "config/timeForNewReleaseCheck",
        ],
        sort_attributes=True,
    )

    root = parse_xml(output_path)

    assert root.find("keep") is not None
    assert root.find("WindowGeometry") is None
    assert root.find("WindowState") is None
    assert root.find("timeForNewReleaseCheck") is None


def test_overlay_retained_nodes_uses_repo_xml_as_base(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.xml"
    live_path = tmp_path / "live.xml"
    output_path = tmp_path / "output.xml"

    repo_path.write_text(
        """<config>
  <keep>repo</keep>
</config>
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """<config>
  <keep>live</keep>
  <WindowGeometry x="100" y="200" />
  <WindowState fullscreen="true" />
  <timeForNewReleaseCheck>12345</timeForNewReleaseCheck>
</config>
""",
        encoding="utf-8",
    )

    MODULE.transform_xml(
        str(repo_path),
        str(output_path),
        overlay_path=str(live_path),
        node_matchers=[
            "config/WindowGeometry",
            "config/WindowState",
            "config/timeForNewReleaseCheck",
        ],
    )

    root = parse_xml(output_path)

    assert root.findtext("keep") == "repo"
    assert root.find("WindowGeometry") is not None
    assert root.find("WindowGeometry").attrib == {"x": "100", "y": "200"}
    assert root.find("WindowState") is not None
    assert root.findtext("timeForNewReleaseCheck") == "12345"


def test_retain_node_matchers_in_strip_mode_keeps_only_selected_paths(tmp_path: Path) -> None:
    input_path = tmp_path / "input.xml"
    output_path = tmp_path / "output.xml"

    input_path.write_text(
        """<config>
  <keep>repo</keep>
  <WindowGeometry x="100" y="200" />
  <Section>
    <KeepNested>value</KeepNested>
    <RetainNested>selected</RetainNested>
  </Section>
</config>
""",
        encoding="utf-8",
    )

    MODULE.transform_xml(
        input_path,
        output_path,
        node_matchers=["config/WindowGeometry", "config/Section/RetainNested"],
        selector_action=MODULE.SelectorAction.RETAIN,
    )

    root = parse_xml(output_path)

    assert root.find("keep") is None
    assert root.find("WindowGeometry") is not None
    assert root.find("Section") is not None
    assert root.find("Section/RetainNested") is not None
    assert root.find("Section/KeepNested") is None


def test_merge_strip_node_matchers_merges_everything_else_from_overlay(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.xml"
    live_path = tmp_path / "live.xml"
    output_path = tmp_path / "output.xml"

    repo_path.write_text(
        """<config>
  <keep>repo</keep>
  <WindowGeometry x="10" y="10" />
</config>
""",
        encoding="utf-8",
    )
    live_path.write_text(
        """<config>
  <keep>live</keep>
  <WindowGeometry x="100" y="200" />
  <WindowState fullscreen="true" />
</config>
""",
        encoding="utf-8",
    )

    MODULE.transform_xml(
        repo_path,
        output_path,
        overlay_path=live_path,
        node_matchers=["config/WindowGeometry"],
        selector_action=MODULE.SelectorAction.STRIP,
    )

    root = parse_xml(output_path)

    assert root.findtext("keep") == "live"
    assert root.find("WindowGeometry").attrib == {"x": "10", "y": "10"}
    assert root.find("WindowState") is not None


def test_overlay_retained_nodes_with_compare_file_preserves_live_order_and_bytes(
    tmp_path: Path,
 ) -> None:
    repo_path = tmp_path / "repo.xml"
    live_path = tmp_path / "live.xml"
    output_path = tmp_path / "output.xml"

    live_text = write_semantically_equal_overlay_xml(repo_path, live_path)

    MODULE.transform_xml(
        str(repo_path),
        str(output_path),
        overlay_path=str(live_path),
        node_matchers=["config/WindowGeometry"],
        compare_path=str(live_path),
    )

    assert output_path.read_text(encoding="utf-8") == live_text


def test_overlay_retained_nodes_without_compare_file_reserializes_semantically_equal_output(
    tmp_path: Path,
 ) -> None:
    repo_path = tmp_path / "repo.xml"
    live_path = tmp_path / "live.xml"
    output_path = tmp_path / "output.xml"

    live_text = write_semantically_equal_overlay_xml(repo_path, live_path)

    MODULE.transform_xml(
        str(repo_path),
        str(output_path),
        overlay_path=str(live_path),
        node_matchers=["config/WindowGeometry"],
    )

    assert output_path.read_text(encoding="utf-8") != live_text
    root = parse_xml(output_path)
    assert root.find("keep") is not None
    assert root.find("keep").attrib == {"id": "1"}
    assert root.find("WindowGeometry") is not None
    assert root.find("WindowGeometry").attrib == {"x": "100", "y": "200"}

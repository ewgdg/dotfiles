from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "xmlformat.py"


def load_module():
    spec = importlib.util.spec_from_file_location("xmlformat", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def parse_xml(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


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

    MODULE.process_xml(
        str(input_path),
        str(output_path),
        node_matchers=[
            "config/WindowGeometry",
            "config/WindowState",
            "config/timeForNewReleaseCheck",
        ],
        sort_attrs=True,
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

    MODULE.process_xml(
        str(repo_path),
        str(output_path),
        overlay_file=str(live_path),
        node_matchers=[
            "config/WindowGeometry",
            "config/WindowState",
            "config/timeForNewReleaseCheck",
        ],
        write_base_unchanged_if_no_effect=True,
    )

    root = parse_xml(output_path)

    assert root.findtext("keep") == "repo"
    assert root.find("WindowGeometry") is not None
    assert root.find("WindowGeometry").attrib == {"x": "100", "y": "200"}
    assert root.find("WindowState") is not None
    assert root.findtext("timeForNewReleaseCheck") == "12345"

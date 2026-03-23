from __future__ import annotations

import importlib.util
from pathlib import Path
import plistlib
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "plist_transform.py"


def load_module():
    spec = importlib.util.spec_from_file_location("plist_transform", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def load_plist(path: Path):
    with path.open("rb") as handle:
        return plistlib.load(handle)


def write_plist(path: Path, data: dict, fmt=plistlib.FMT_XML) -> None:
    with path.open("wb") as handle:
        plistlib.dump(data, handle, fmt=fmt, sort_keys=True)


def test_plist_engine_declares_typed_selectors() -> None:
    selector_specs = {spec.name: spec for spec in MODULE.PlistTransformEngine.selector_specs()}

    assert selector_specs["key"].prefix == "exact"


def test_compare_file_preserves_existing_bytes(tmp_path: Path) -> None:
    input_path = tmp_path / "input.plist"
    compare_path = tmp_path / "compare.plist"
    output_path = tmp_path / "output.plist"

    write_plist(input_path, {"Alpha": 1}, fmt=plistlib.FMT_BINARY)
    compare_path.write_bytes(input_path.read_bytes())

    exit_code = MODULE.main(
        [
            str(input_path),
            str(output_path),
            "--mode",
            "strip",
            "--compare-file",
            str(compare_path),
            "--output-format",
            "xml",
        ]
    )

    assert exit_code == 0
    assert output_path.read_bytes() == compare_path.read_bytes()


def test_strip_mode_without_compare_file_reserializes_requested_format(
    tmp_path: Path,
 ) -> None:
    input_path = tmp_path / "input.plist"
    output_path = tmp_path / "output.plist"

    write_plist(input_path, {"Alpha": 1}, fmt=plistlib.FMT_BINARY)

    exit_code = MODULE.main(
        [
            str(input_path),
            str(output_path),
            "--mode",
            "cleanup",
            "--output-format",
            "xml",
        ]
    )

    assert exit_code == 0
    assert load_plist(output_path) == {"Alpha": 1}
    assert output_path.read_bytes().startswith(b"<?xml")


def test_merge_mode_without_compare_file_reserializes_requested_format(
    tmp_path: Path,
 ) -> None:
    repo_path = tmp_path / "repo.plist"
    live_path = tmp_path / "live.plist"
    output_path = tmp_path / "output.plist"

    write_plist(repo_path, {"Alpha": 1})
    write_plist(live_path, {"Alpha": 1}, fmt=plistlib.FMT_BINARY)

    exit_code = MODULE.main(
        [
            str(repo_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(live_path),
            "--output-format",
            "xml",
        ]
    )

    assert exit_code == 0
    assert load_plist(output_path) == {"Alpha": 1}
    assert output_path.read_bytes().startswith(b"<?xml")


def test_strip_mode_retain_key_keeps_only_selected_keys(tmp_path: Path) -> None:
    input_path = tmp_path / "input.plist"
    output_path = tmp_path / "output.plist"

    write_plist(
        input_path,
        {
            "bypassEventsFromOtherApplications": True,
            "SULastCheckTime": "noise",
        },
    )

    exit_code = MODULE.main(
        [
            str(input_path),
            str(output_path),
            "--mode",
            "cleanup",
            "--selector-type",
            "retain",
            "--selectors",
            "bypassEventsFromOtherApplications",
        ]
    )

    assert exit_code == 0
    assert load_plist(output_path) == {"bypassEventsFromOtherApplications": True}


def test_merge_mode_retain_key_merges_selected_overlay_keys(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.plist"
    live_path = tmp_path / "live.plist"
    output_path = tmp_path / "output.plist"

    write_plist(repo_path, {"KeepRepo": "repo", "bypassEventsFromOtherApplications": False})
    write_plist(
        live_path,
        {
            "KeepRepo": "live",
            "bypassEventsFromOtherApplications": True,
            "SULastCheckTime": "noise",
        },
        fmt=plistlib.FMT_BINARY,
    )

    exit_code = MODULE.main(
        [
            str(repo_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(live_path),
            "--output-format",
            "binary",
            "--selector-type",
            "retain",
            "--selectors",
            "bypassEventsFromOtherApplications",
        ]
    )

    assert exit_code == 0
    assert load_plist(output_path) == {
        "KeepRepo": "live",
        "bypassEventsFromOtherApplications": False,
        "SULastCheckTime": "noise",
    }


def test_merge_mode_strip_key_merges_everything_else_from_overlay(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo.plist"
    live_path = tmp_path / "live.plist"
    output_path = tmp_path / "output.plist"

    write_plist(repo_path, {"KeepRepo": "repo", "WindowGeometry": "repo-geometry"})
    write_plist(
        live_path,
        {
            "KeepRepo": "live",
            "WindowGeometry": "noise",
            "WindowState": "fullscreen",
        },
    )

    exit_code = MODULE.main(
        [
            str(repo_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(live_path),
            "--selector-type",
            "remove",
            "--selectors",
            "WindowGeometry",
        ]
    )

    assert exit_code == 0
    assert load_plist(output_path) == {
        "KeepRepo": "repo",
        "WindowGeometry": "noise",
        "WindowState": "fullscreen",
    }

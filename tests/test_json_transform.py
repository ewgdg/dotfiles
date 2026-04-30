from __future__ import annotations

import json
from pathlib import Path

from scripts import json_transform as MODULE


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_json_engine_declares_typed_selectors() -> None:
    selector_specs = {spec.name: spec for spec in MODULE.JsonTransformEngine.selector_specs()}

    assert selector_specs["key"].prefix == "exact"
    assert selector_specs["key_regex"].prefix == "re"


def test_compare_file_preserves_existing_text(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    compare_path = tmp_path / "compare.json"
    output_path = tmp_path / "output.json"

    input_path.write_text('{"alpha":1,"beta":true}\n', encoding="utf-8")
    compare_path.write_text('{\n  "alpha": 1,\n  "beta": true\n}\n', encoding="utf-8")

    exit_code = MODULE.main(
        [
            str(input_path),
            str(output_path),
            "--mode",
            "cleanup",
            "--compare-file",
            str(compare_path),
        ]
    )

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8") == compare_path.read_text(encoding="utf-8")


def test_cleanup_remove_key_strips_selected_top_level_keys(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"

    input_path.write_text(
        json.dumps(
            {
                "aururl": "https://aur.archlinux.org",
                "buildDir": "/tmp/yay",
                "version": "12.5.7",
                "bottomup": True,
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(input_path),
            str(output_path),
            "--mode",
            "cleanup",
            "--selector-type",
            "remove",
            "--selectors",
            "buildDir",
        ]
    )

    assert exit_code == 0
    assert load_json(output_path) == {
        "aururl": "https://aur.archlinux.org",
        "version": "12.5.7",
        "bottomup": True,
    }


def test_cleanup_remove_key_regex_strips_matching_top_level_keys(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"

    input_path.write_text(
        json.dumps(
            {
                "WindowGeometry": "noise",
                "WindowState": "noise",
                "keep": True,
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(input_path),
            str(output_path),
            "--mode",
            "cleanup",
            "--selector-type",
            "remove",
            "--selectors",
            r"re:^Window",
        ]
    )

    assert exit_code == 0
    assert load_json(output_path) == {"keep": True}


def test_merge_retain_key_preserves_selected_live_keys_and_reapplies_repo_content(
    tmp_path: Path,
) -> None:
    live_path = tmp_path / "live.json"
    repo_path = tmp_path / "repo.json"
    output_path = tmp_path / "output.json"

    live_path.write_text(
        json.dumps(
            {
                "aururl": "https://aur.archlinux.org",
                "buildDir": "/home/test/.cache/yay",
                "version": "11.0.0",
                "bottomup": False,
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )
    repo_path.write_text(
        json.dumps(
            {
                "aururl": "https://aur.archlinux.org",
                "version": "12.5.7",
                "bottomup": True,
                "rpc": True,
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(live_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(repo_path),
            "--selector-type",
            "retain",
            "--selectors",
            "buildDir",
        ]
    )

    assert exit_code == 0
    assert load_json(output_path) == {
        "aururl": "https://aur.archlinux.org",
        "buildDir": "/home/test/.cache/yay",
        "version": "12.5.7",
        "bottomup": True,
        "rpc": True,
    }


def test_merge_retain_key_regex_preserves_matching_live_keys_and_reapplies_repo_content(
    tmp_path: Path,
) -> None:
    live_path = tmp_path / "live.json"
    repo_path = tmp_path / "repo.json"
    output_path = tmp_path / "output.json"

    live_path.write_text(
        json.dumps(
            {
                "WindowGeometry": "live-geometry",
                "WindowState": "live-state",
                "managed": "stale",
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )
    repo_path.write_text(
        json.dumps({"managed": "repo"}, indent="\t") + "\n",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(live_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(repo_path),
            "--selector-type",
            "retain",
            "--selectors",
            r"re:^Window",
        ]
    )

    assert exit_code == 0
    assert load_json(output_path) == {
        "WindowGeometry": "live-geometry",
        "WindowState": "live-state",
        "managed": "repo",
    }


def test_merge_retain_key_preserves_live_order_and_drops_deleted_repo_keys(
    tmp_path: Path,
) -> None:
    live_path = tmp_path / "live.json"
    repo_path = tmp_path / "repo.json"
    output_path = tmp_path / "output.json"

    live_path.write_text(
        json.dumps(
            {
                "aururl": "https://aur.archlinux.org",
                "aurrpcurl": "https://aur.archlinux.org/rpc?",
                "buildDir": "/home/test/.cache/yay",
                "editor": "nano",
                "useask": False,
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )
    repo_path.write_text(
        json.dumps(
            {
                "aururl": "https://aur.archlinux.org",
                "aurrpcurl": "https://aur.archlinux.org/rpc?",
                "editor": "",
                "useask": True,
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(live_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(repo_path),
            "--selector-type",
            "retain",
            "--selectors",
            "buildDir",
        ]
    )

    assert exit_code == 0
    merged_data = load_json(output_path)
    assert list(merged_data) == ["aururl", "aurrpcurl", "buildDir", "editor", "useask"]
    assert merged_data == {
        "aururl": "https://aur.archlinux.org",
        "aurrpcurl": "https://aur.archlinux.org/rpc?",
        "buildDir": "/home/test/.cache/yay",
        "editor": "",
        "useask": True,
    }


def test_merge_remove_key_preserves_unselected_live_keys(tmp_path: Path) -> None:
    live_path = tmp_path / "live.json"
    repo_path = tmp_path / "repo.json"
    output_path = tmp_path / "output.json"

    live_path.write_text(
        json.dumps(
            {
                "keepLocal": "noise",
                "buildDir": "/home/test/.cache/yay",
                "version": "11.0.0",
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )
    repo_path.write_text(
        json.dumps(
            {
                "version": "12.5.7",
                "rpc": True,
            },
            indent="\t",
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = MODULE.main(
        [
            str(live_path),
            str(output_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(repo_path),
            "--selector-type",
            "remove",
            "--selectors",
            "buildDir",
        ]
    )

    assert exit_code == 0
    assert load_json(output_path) == {
        "keepLocal": "noise",
        "version": "12.5.7",
        "rpc": True,
    }

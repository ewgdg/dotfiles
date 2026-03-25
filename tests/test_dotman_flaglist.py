from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dotman.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dotman_flaglist", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def test_flag_list_normalizes_known_split_value_options() -> None:
    normalized_args = MODULE.FlagList.normalize_args(
        [
            "compare",
            "--profile",
            "repro",
            "-c",
            "/tmp/config.yaml",
            "-w",
            "4",
            "-i",
            "*.bak",
        ]
    )

    assert normalized_args == [
        "compare",
        "--profile=repro",
        "--cfg=/tmp/config.yaml",
        "--workers=4",
        "--ignore=*.bak",
    ]


def test_flag_list_keeps_unknown_split_flags_and_literal_args_unchanged() -> None:
    normalized_args = MODULE.FlagList.normalize_args(
        [
            "compare",
            "-C",
            "/tmp/example.toml",
            "--",
            "--profile",
            "repro",
        ]
    )

    assert normalized_args == [
        "compare",
        "-C",
        "/tmp/example.toml",
        "--",
        "--profile",
        "repro",
    ]


def test_flag_list_append_if_absent_does_not_replace_existing_option() -> None:
    flags = MODULE.FlagList()

    flags.extend(["compare", "--profile", "repro", "d_app"])
    flags.append_if_absent("--profile=resolved")

    assert list(flags) == [
        "compare",
        "--profile=repro",
        "d_app",
    ]


def test_flag_list_append_if_absent_appends_missing_option() -> None:
    flags = MODULE.FlagList()

    flags.extend(["compare", "d_app"])
    flags.append_if_absent("--profile=resolved")

    assert list(flags) == [
        "compare",
        "d_app",
        "--profile=resolved",
    ]

from __future__ import annotations

from scripts import dotman as MODULE


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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib
from typing import Any, Iterable

import tomlkit


def collect_template_placeholders(
    value: Any,
    *,
    placeholder_prefix: str,
    path: tuple[Any, ...] = (),
) -> Iterable[tuple[tuple[Any, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from collect_template_placeholders(child, placeholder_prefix=placeholder_prefix, path=(*path, key))
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from collect_template_placeholders(child, placeholder_prefix=placeholder_prefix, path=(*path, index))
        return

    if isinstance(value, str) and value.startswith(placeholder_prefix):
        yield path, value


def assign_path(target: Any, path: tuple[Any, ...], value: str) -> None:
    cursor = target
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def capture_greetd_config(live_text: str, template_text: str, *, placeholder_prefix: str) -> str:
    template_data = tomllib.loads(template_text)
    live_document = tomlkit.parse(live_text)

    template_placeholders = list(
        collect_template_placeholders(template_data, placeholder_prefix=placeholder_prefix)
    )
    if not template_placeholders:
        raise ValueError(f"template has no placeholders with prefix: {placeholder_prefix}")

    for path, placeholder_value in template_placeholders:
        assign_path(live_document, path, placeholder_value)

    return tomlkit.dumps(live_document)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture greetd config back into repo template form."
    )
    parser.add_argument("live_path", type=Path, help="Path to live greetd config.")
    parser.add_argument(
        "--template-file",
        required=True,
        type=Path,
        help="Path to repo template used to restore placeholder fields.",
    )
    parser.add_argument(
        "--placeholder-prefix",
        default="__PLACEHOLDER_",
        help="Prefix used to detect placeholder values in template source.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        live_text = args.live_path.read_text(encoding="utf-8")
        template_text = args.template_file.read_text(encoding="utf-8")
        captured_text = capture_greetd_config(
            live_text,
            template_text,
            placeholder_prefix=args.placeholder_prefix,
        )
    except Exception as exc:
        print(f"capture_greetd_config: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(captured_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

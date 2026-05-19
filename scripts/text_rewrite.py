#!/usr/bin/env python3
"""Small text rewrite filters for dotman render/capture pipelines."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
from typing import Callable


# Characters that can be part of a path segment. Home rewrites require a boundary
# before/after the matched prefix so /home/alice does not rewrite inside
# /mnt/home/alice or /home/alice-other.
_PATH_FRAGMENT_CHARS = r"A-Za-z0-9._~/-"


def normalize_home(home: str | None = None) -> str:
    raw_home = home if home is not None else os.environ.get("HOME", "")
    normalized_home = raw_home.rstrip("/")
    if not normalized_home or normalized_home == "/":
        raise ValueError("HOME must be set to a non-root absolute path")
    if not normalized_home.startswith("/"):
        raise ValueError("HOME must be an absolute path")
    return normalized_home


def collapse_home_paths(text: str, *, home: str | None = None) -> str:
    normalized_home = normalize_home(home)
    pattern = re.compile(
        rf"(?<![{_PATH_FRAGMENT_CHARS}]){re.escape(normalized_home)}(?=$|/|[^{_PATH_FRAGMENT_CHARS}])"
    )
    return pattern.sub("~", text)


def expand_home_paths(text: str, *, home: str | None = None) -> str:
    normalized_home = normalize_home(home)
    pattern = re.compile(rf"(?<![{_PATH_FRAGMENT_CHARS}])~(?=$|/|[^{_PATH_FRAGMENT_CHARS}])")
    return pattern.sub(normalized_home, text)


def apply_literal_replacement(text: str, *, old: str, new: str) -> str:
    if old == "":
        raise ValueError("literal replacement source must not be empty")
    return text.replace(old, new)


def apply_regex_replacement(text: str, *, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, text)


def read_text(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    return path.read_text(encoding="utf-8")


def emit_text(text: str, output_path: Path | None, *, stdout: bool = False) -> None:
    if stdout or output_path is None:
        sys.stdout.write(text)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def rewrite_io(
    transform: Callable[[str], str],
    *,
    input_path: Path | None,
    output_path: Path | None,
    stdout: bool,
) -> None:
    emit_text(transform(read_text(input_path)), output_path, stdout=stdout)


def add_io_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        help="Input file. Defaults to stdin.",
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        type=Path,
        help="Output file. Defaults to stdout.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write to stdout even when output_path is provided.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply small text rewrites for dotman pipelines.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    home_parser = subparsers.add_parser("home", help="Rewrite home-directory path fragments.")
    home_subparsers = home_parser.add_subparsers(dest="home_command", required=True)

    for name in ("collapse", "expand"):
        command_parser = home_subparsers.add_parser(name)
        add_io_arguments(command_parser)
        command_parser.add_argument(
            "--home",
            help="Home directory to use instead of $HOME. Mostly useful for tests.",
        )

    replace_parser = subparsers.add_parser("replace", help="Apply a literal or regex text replacement.")
    add_io_arguments(replace_parser)
    replacement_group = replace_parser.add_mutually_exclusive_group(required=True)
    replacement_group.add_argument("--literal", metavar="TEXT", help="Literal text to replace.")
    replacement_group.add_argument("--regex", metavar="PATTERN", help="Regex pattern to replace.")
    replace_parser.add_argument(
        "--with",
        dest="replacement",
        required=True,
        help="Replacement text.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "home" and args.home_command == "collapse":
            rewrite_io(
                lambda text: collapse_home_paths(text, home=args.home),
                input_path=args.input_path,
                output_path=args.output_path,
                stdout=args.stdout,
            )
            return 0

        if args.command == "home" and args.home_command == "expand":
            rewrite_io(
                lambda text: expand_home_paths(text, home=args.home),
                input_path=args.input_path,
                output_path=args.output_path,
                stdout=args.stdout,
            )
            return 0

        if args.command == "replace":
            if args.literal is not None:
                transform = lambda text: apply_literal_replacement(
                    text,
                    old=args.literal,
                    new=args.replacement,
                )
            else:
                transform = lambda text: apply_regex_replacement(
                    text,
                    pattern=args.regex,
                    replacement=args.replacement,
                )
            rewrite_io(
                transform,
                input_path=args.input_path,
                output_path=args.output_path,
                stdout=args.stdout,
            )
            return 0
    except ValueError as error:
        print(f"text_rewrite: {error}", file=sys.stderr)
        return 2

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

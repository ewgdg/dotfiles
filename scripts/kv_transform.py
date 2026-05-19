#!/usr/bin/env python3
"""Line-based key=value transform for dotman render/capture pipelines."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from scripts.text_rewrite import collapse_home_paths, expand_home_paths


KEY_VALUE_PATTERN = re.compile(r"^(?P<key>[^=\s][^=]*?)\s*=\s*(?P<value>.*)$")
QUOTED_VALUE_PATTERN = re.compile(r'^(?P<quote>["\'])(?P<value>.*)(?P=quote)$')


@dataclass(frozen=True)
class ConfigLine:
    original: str
    key: str | None = None
    value: str | None = None
    quote: str = ""

    def with_value(self, value: str, *, quote: str | None = None) -> str:
        if self.key is None:
            return self.original
        quote_style = self.quote if quote is None else quote
        return f"{self.key}={quote_style}{value}{quote_style}"


def parse_config_lines(config_text: str) -> list[ConfigLine]:
    lines: list[ConfigLine] = []
    for raw_line in config_text.splitlines():
        if raw_line.lstrip().startswith(("#", ";")):
            lines.append(ConfigLine(original=raw_line))
            continue

        match = KEY_VALUE_PATTERN.match(raw_line)
        if match is None:
            lines.append(ConfigLine(original=raw_line))
            continue

        raw_value = match.group("value").strip()
        quoted = QUOTED_VALUE_PATTERN.match(raw_value)
        if quoted is None:
            value = raw_value
            quote = ""
        else:
            value = quoted.group("value")
            quote = quoted.group("quote")

        lines.append(
            ConfigLine(
                original=raw_line,
                key=match.group("key").strip(),
                value=value,
                quote=quote,
            )
        )

    return lines


def collect_key_values(lines: Iterable[ConfigLine]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if line.key is None or line.value is None:
            continue
        values[line.key] = line.value
    return values


def validate_required_keys(values: dict[str, str], required_keys: set[str]) -> None:
    missing_keys = sorted(required_keys - set(values))
    if missing_keys:
        raise ValueError(f"missing required keys: {', '.join(missing_keys)}")


def normalize_values_for_render(
    values: dict[str, str],
    *,
    home_expand_keys: set[str],
) -> dict[str, str]:
    return {
        key: expand_home_paths(value) if key in home_expand_keys else value
        for key, value in values.items()
    }


def render_config_text(
    repo_text: str,
    *,
    live_text: str | None = None,
    home_expand_keys: set[str] | None = None,
    require_keys: set[str] | None = None,
) -> str:
    home_expand_keys = home_expand_keys or set()
    require_keys = require_keys or set()

    repo_lines = parse_config_lines(repo_text)
    repo_values = collect_key_values(repo_lines)
    validate_required_keys(repo_values, require_keys)
    repo_values = normalize_values_for_render(
        repo_values,
        home_expand_keys=home_expand_keys,
    )

    if live_text is None:
        rendered_lines = [
            line.with_value(repo_values[line.key], quote=line.quote)
            if line.key in repo_values
            else line.original
            for line in repo_lines
        ]
        return "\n".join(rendered_lines).rstrip("\n") + "\n"

    live_lines = parse_config_lines(live_text)
    rendered_lines: list[str] = []
    seen_managed_keys: set[str] = set()

    for live_line in live_lines:
        if live_line.key is None:
            rendered_lines.append(live_line.original)
            continue
        if live_line.key in repo_values:
            rendered_lines.append(live_line.with_value(repo_values[live_line.key]))
            seen_managed_keys.add(live_line.key)
        else:
            rendered_lines.append(live_line.original)

    for repo_line in repo_lines:
        if repo_line.key is None or repo_line.key in seen_managed_keys:
            continue
        rendered_lines.append(repo_line.with_value(repo_values[repo_line.key]))

    return "\n".join(rendered_lines).rstrip("\n") + "\n"


def capture_config_text(
    live_text: str,
    *,
    remove_keys: set[str] | None = None,
    home_collapse_keys: set[str] | None = None,
    require_keys: set[str] | None = None,
) -> str:
    remove_keys = remove_keys or set()
    home_collapse_keys = home_collapse_keys or set()
    require_keys = require_keys or set()

    live_lines = parse_config_lines(live_text)
    live_values = collect_key_values(live_lines)
    validate_required_keys(live_values, require_keys)

    captured_lines: list[str] = []
    for line in live_lines:
        if line.key in remove_keys:
            continue
        if line.key in home_collapse_keys:
            if line.value is None:
                raise ValueError(f"key has no value: {line.key}")
            captured_lines.append(line.with_value(collapse_home_paths(line.value)))
            continue
        captured_lines.append(line.original)

    return "\n".join(captured_lines).rstrip("\n") + "\n"


def read_optional_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def add_key_list_argument(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(
        name,
        nargs="*",
        default=(),
        metavar="KEY",
        help=help_text,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render/capture line-based key=value config files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("repo_path", type=Path)
    render_parser.add_argument("--live-path", type=Path)
    add_key_list_argument(
        render_parser,
        "--home-expand-keys",
        "Keys whose values should expand ~/... to $HOME/... during render.",
    )
    add_key_list_argument(
        render_parser,
        "--require-keys",
        "Keys required by this transform invocation during render; missing keys fail fast.",
    )

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("live_path", type=Path)
    add_key_list_argument(
        capture_parser,
        "--remove-keys",
        "Keys to omit from captured output.",
    )
    add_key_list_argument(
        capture_parser,
        "--home-collapse-keys",
        "Keys whose values should collapse $HOME/... to ~/... during capture.",
    )
    add_key_list_argument(
        capture_parser,
        "--require-keys",
        "Keys required by this transform invocation during capture; missing keys fail fast.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "render":
            sys.stdout.write(
                render_config_text(
                    args.repo_path.read_text(encoding="utf-8"),
                    live_text=read_optional_text(args.live_path),
                    home_expand_keys=set(args.home_expand_keys),
                    require_keys=set(args.require_keys),
                )
            )
            return 0

        if args.command == "capture":
            sys.stdout.write(
                capture_config_text(
                    args.live_path.read_text(encoding="utf-8"),
                    remove_keys=set(args.remove_keys),
                    home_collapse_keys=set(args.home_collapse_keys),
                    require_keys=set(args.require_keys),
                )
            )
            return 0
    except ValueError as error:
        print(f"kv_transform: {error}", file=sys.stderr)
        return 2

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

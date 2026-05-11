#!/usr/bin/env python3
"""Render/capture Faugus Launcher config with repo-stable home-relative paths."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
import re
import sys


STATE_KEYS = frozenset({"donate-last", "playtime"})
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


def home_dir() -> str:
    home = os.environ.get("HOME")
    if not home:
        raise RuntimeError("HOME is required to render Faugus config paths")
    return home.rstrip("/") or "/"


def expand_home_relative_path(path_value: str) -> str:
    if path_value == "~":
        return home_dir()
    if path_value.startswith("~/"):
        return f"{home_dir()}/{path_value[2:]}"
    return path_value


def collapse_home_path(path_value: str) -> str:
    home = home_dir()
    if path_value == home:
        return "~"
    home_prefix = f"{home}/"
    if path_value.startswith(home_prefix):
        return f"~/{path_value[len(home_prefix):]}"
    return path_value


def collect_key_values(lines: list[ConfigLine]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if line.key is None or line.value is None:
            continue
        values[line.key] = line.value
    return values


def normalize_default_prefix_for_render(values: dict[str, str]) -> dict[str, str]:
    if "default-prefix" not in values:
        raise ValueError("Faugus config template must include default-prefix")
    return {
        key: expand_home_relative_path(value) if key == "default-prefix" else value
        for key, value in values.items()
    }


def render_config_text(repo_text: str, *, live_text: str | None = None) -> str:
    repo_lines = parse_config_lines(repo_text)
    repo_values = normalize_default_prefix_for_render(collect_key_values(repo_lines))

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
            # Preserve Faugus runtime state and future config keys not yet tracked here.
            rendered_lines.append(live_line.original)

    for repo_line in repo_lines:
        if repo_line.key is None or repo_line.key in seen_managed_keys:
            continue
        rendered_lines.append(repo_line.with_value(repo_values[repo_line.key]))

    return "\n".join(rendered_lines).rstrip("\n") + "\n"


def capture_config_text(live_text: str) -> str:
    captured_lines: list[str] = []
    saw_default_prefix = False

    for line in parse_config_lines(live_text):
        if line.key in STATE_KEYS:
            continue
        if line.key == "default-prefix":
            if line.value is None:
                raise ValueError("default-prefix line has no value")
            captured_lines.append(line.with_value(collapse_home_path(line.value)))
            saw_default_prefix = True
        else:
            captured_lines.append(line.original)

    if not saw_default_prefix:
        raise ValueError("Faugus config must include default-prefix")

    return "\n".join(captured_lines).rstrip("\n") + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render/capture Faugus Launcher config with home-relative repo paths."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("repo_path", type=Path)
    render_parser.add_argument("--live-path", type=Path)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("live_path", type=Path)

    return parser


def read_optional_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "render":
        sys.stdout.write(
            render_config_text(
                args.repo_path.read_text(encoding="utf-8"),
                live_text=read_optional_text(args.live_path),
            )
        )
        return 0

    if args.command == "capture":
        sys.stdout.write(capture_config_text(args.live_path.read_text(encoding="utf-8")))
        return 0

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

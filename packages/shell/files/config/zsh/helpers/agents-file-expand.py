#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


BARE_REFERENCE_LINE_PATTERN = re.compile(r"""^\s*@([^\s<>{}\[\]"'`(),;!?]+)\s*$""")
QUOTED_REFERENCE_LINE_PATTERN = re.compile(r"""^\s*@(["'])(.*)\1\s*$""")
DEFAULT_TARGET = "codex"


def default_input_path(target: str) -> Path:
    return Path(f"~/.{target}/AGENTS.md").expanduser()


def default_output_path(target: str) -> Path:
    return Path(f"~/.{target}/AGENTS.override.md").expanduser()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand whole-line @file markers inside a Markdown file.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"target app name used to derive default paths (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="output path (default: ~/.<target>/AGENTS.override.md)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="input path (default: ~/.<target>/AGENTS.md)",
    )
    return parser.parse_args(argv)


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: str | None = None
    if path.is_file() or path.is_symlink():
        try:
            existing = read_text(path)
        except OSError:
            existing = None

    if existing == content:
        return

    if path.is_symlink():
        path.unlink()

    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def file_exists(path: Path) -> bool:
    return path.is_file()


def canonicalize(path: Path) -> Path:
    return Path(os.path.realpath(path))


def resolve_reference_path(reference: str, base_dir: Path) -> Path:
    env_match = re.match(r"^\$(\w+)(.*)$", reference) or re.match(r"^\$\{([^}]+)\}(.*)$", reference)
    if env_match:
        env_name = env_match.group(1)
        suffix = env_match.group(2) or ""
        env_value = os.environ.get(env_name)
        if env_value:
            candidate = Path(env_value + suffix)
            if candidate.is_absolute():
                return candidate
            return (base_dir / candidate).resolve()

    if reference == "~":
        return Path.home()
    if reference.startswith("~/"):
        return Path.home() / reference[2:]

    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def unescape_quoted_reference(raw: str) -> str:
    parts: list[str] = []
    cursor = 0

    while cursor < len(raw):
        current = raw[cursor]
        if current == "\\" and cursor + 1 < len(raw):
            parts.append(raw[cursor + 1])
            cursor += 2
            continue

        parts.append(current)
        cursor += 1

    return "".join(parts)


def parse_whole_line_reference(line: str) -> str | None:
    quoted_match = QUOTED_REFERENCE_LINE_PATTERN.match(line)
    if quoted_match:
        reference = unescape_quoted_reference(quoted_match.group(2))
        return reference or None

    bare_match = BARE_REFERENCE_LINE_PATTERN.match(line)
    if bare_match:
        return bare_match.group(1)

    return None


def ends_with_line_break(text: str) -> bool:
    return bool(re.search(r"\r?\n$", text))


def expand_text(
    text: str,
    base_dir: Path,
    source_path: Path,
    memo: dict[Path, str],
    issues: list[str],
    stack: list[Path],
) -> str:
    segments = re.split(r"(\r?\n)", text)
    chunks: list[str] = []

    for index in range(0, len(segments), 2):
        body = segments[index] if index < len(segments) else ""
        newline = segments[index + 1] if index + 1 < len(segments) else ""
        expanded = expand_line(body, base_dir, source_path, memo, issues, stack)
        chunks.append(expanded)
        if newline and not ends_with_line_break(expanded):
            chunks.append(newline)

    return "".join(chunks)


def expand_line(
    line: str,
    base_dir: Path,
    source_path: Path,
    memo: dict[Path, str],
    issues: list[str],
    stack: list[Path],
) -> str:
    reference = parse_whole_line_reference(line)
    if not reference:
        return line

    resolved_path = resolve_reference_path(reference, base_dir)
    if not file_exists(resolved_path):
        issues.append(f"Missing reference in {source_path}: @{reference}")
        return line

    try:
        return load_expanded_file(resolved_path, memo, issues, stack)
    except Exception as error:  # noqa: BLE001 - keep original marker on any expansion failure
        issues.append(f"Failed to expand @{reference} from {source_path}: {error}")
        return line


def load_expanded_file(
    file_path: Path,
    memo: dict[Path, str],
    issues: list[str],
    stack: list[Path],
) -> str:
    canonical_path = canonicalize(file_path)
    cached = memo.get(canonical_path)
    if cached is not None:
        return cached

    if canonical_path in stack:
        cycle = " -> ".join(str(path) for path in [*stack, canonical_path])
        raise RuntimeError(f"cycle while expanding {cycle}")

    stack.append(canonical_path)
    raw = read_text(canonical_path)
    expanded = expand_text(raw, canonical_path.parent, canonical_path, memo, issues, stack)
    stack.pop()
    memo[canonical_path] = expanded
    return expanded


def expand_input(input_path: Path) -> tuple[str, list[str]]:
    if not input_path.exists():
        return "", []

    if not input_path.is_file():
        raise ValueError(f"input is not a file: {input_path}")

    memo: dict[Path, str] = {}
    issues: list[str] = []
    expanded = load_expanded_file(input_path, memo, issues, [])
    return expanded, issues


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_path = Path(args.input).expanduser() if args.input else default_input_path(args.target)
    output_path = Path(args.output).expanduser() if args.output else default_output_path(args.target)

    try:
        expanded, issues = expand_input(input_path)
    except Exception as error:  # noqa: BLE001 - CLI should report cleanly
        print(f"codex-agents-expand: {error}", file=sys.stderr)
        return 1

    write_text_if_changed(output_path, expanded)

    for issue in issues:
        print(f"codex-agents-expand: {issue}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

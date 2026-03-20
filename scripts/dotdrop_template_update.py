#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


TEMPLATE_BLOCK_RE = re.compile(r"(\{\{@@.*?@@\}\}|\{%@@.*?@@%\}|\{#@@.*?@@#\})")
CONTROL_LINE_RE = re.compile(r"^(?:\s*)(\{%@@.*?@@%\}|\{#@@.*?@@#\})(?:\s*)$")


@dataclass(frozen=True)
class SourceLine:
    index: int
    text: str
    kind: str
    literal_text: str
    anchor_pattern: re.Pattern[str] | None


@dataclass(frozen=True)
class MatchPair:
    source_index: int
    live_index: int


@dataclass(frozen=True)
class BlockRange:
    start: int
    end: int


@dataclass
class MergeStats:
    matched_lines: int = 0
    whole_block_replacements: int = 0
    partial_block_merges: int = 0
    unchanged_blocks: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Heuristically merge a rendered live file back into a dotdrop template source. "
            "Template control blocks are preserved and only literal sections are updated."
        )
    )
    parser.add_argument("template_path", type=Path, help="Template source file in the repo.")
    parser.add_argument("live_path", type=Path, help="Rendered file from the live filesystem.")
    parser.add_argument(
        "output_path",
        nargs="?",
        type=Path,
        help="Where to write the merged template. Defaults to overwriting template_path.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite template_path directly.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the merged result to stdout instead of writing a file.",
    )
    return parser.parse_args()


def load_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def classify_source_line(index: int, text: str) -> SourceLine:
    stripped_line = text.rstrip("\n")
    literal_text = TEMPLATE_BLOCK_RE.sub("", stripped_line)

    if CONTROL_LINE_RE.fullmatch(stripped_line):
        return SourceLine(index, text, "control", literal_text, None)

    if TEMPLATE_BLOCK_RE.search(stripped_line):
        anchor_pattern = compile_anchor_pattern(stripped_line, literal_text)
        return SourceLine(index, text, "mixed", literal_text, anchor_pattern)

    return SourceLine(index, text, "literal", literal_text, None)


def compile_anchor_pattern(line: str, literal_text: str) -> re.Pattern[str] | None:
    literal_weight = len(re.sub(r"\s+", "", literal_text))
    if literal_weight < 4:
        return None

    parts = TEMPLATE_BLOCK_RE.split(line)
    pattern_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if TEMPLATE_BLOCK_RE.fullmatch(part):
            pattern_parts.append(".*?")
        else:
            pattern_parts.append(re.escape(part))

    return re.compile("^" + "".join(pattern_parts) + "$")


def build_source_lines(lines: list[str]) -> list[SourceLine]:
    return [classify_source_line(index, text) for index, text in enumerate(lines)]


def build_matchable_indices(source_lines: list[SourceLine]) -> list[int]:
    indices: list[int] = []
    for source_line in source_lines:
        if source_line.kind == "literal":
            indices.append(source_line.index)
            continue
        if source_line.kind == "mixed" and source_line.anchor_pattern is not None:
            indices.append(source_line.index)
    return indices


def line_matches(source_line: SourceLine, live_line: str) -> bool:
    source_text = source_line.text.rstrip("\n")
    live_text = live_line.rstrip("\n")

    if source_line.kind == "literal":
        return source_text == live_text

    if source_line.anchor_pattern is None:
        return False

    return bool(source_line.anchor_pattern.fullmatch(live_text))


def match_weight(source_line: SourceLine) -> int:
    if source_line.kind == "literal":
        return 4
    return 1


def align_source_to_live(source_lines: list[SourceLine], live_lines: list[str]) -> list[MatchPair]:
    matchable_indices = build_matchable_indices(source_lines)
    source_items = [source_lines[index] for index in matchable_indices]
    live_items = [line.rstrip("\n") for line in live_lines]

    if not source_items or not live_items:
        return []

    rows = len(source_items) + 1
    cols = len(live_items) + 1
    dp = [[0] * cols for _ in range(rows)]

    for source_pos, source_line in enumerate(source_items, start=1):
        for live_pos, live_line in enumerate(live_items, start=1):
            best_score = max(dp[source_pos - 1][live_pos], dp[source_pos][live_pos - 1])
            if line_matches(source_line, live_line):
                best_score = max(best_score, dp[source_pos - 1][live_pos - 1] + match_weight(source_line))
            dp[source_pos][live_pos] = best_score

    matches: list[MatchPair] = []
    source_pos = len(source_items)
    live_pos = len(live_items)
    while source_pos > 0 and live_pos > 0:
        source_line = source_items[source_pos - 1]
        live_line = live_items[live_pos - 1]
        if line_matches(source_line, live_line):
            expected = dp[source_pos - 1][live_pos - 1] + match_weight(source_line)
            if dp[source_pos][live_pos] == expected:
                matches.append(MatchPair(source_line.index, live_pos - 1))
                source_pos -= 1
                live_pos -= 1
                continue

        if dp[source_pos - 1][live_pos] >= dp[source_pos][live_pos - 1]:
            source_pos -= 1
        else:
            live_pos -= 1

    matches.reverse()
    return matches


def find_literal_blocks(source_lines: list[SourceLine]) -> list[BlockRange]:
    blocks: list[BlockRange] = []
    block_start: int | None = None
    for source_line in source_lines:
        if source_line.kind == "literal":
            if block_start is None:
                block_start = source_line.index
            continue

        if block_start is not None:
            blocks.append(BlockRange(block_start, source_line.index))
            block_start = None

    if block_start is not None:
        blocks.append(BlockRange(block_start, len(source_lines)))

    return blocks


def merge_literal_block(
    block: BlockRange,
    source_lines: list[SourceLine],
    live_lines: list[str],
    matches: list[MatchPair],
    matched_source_indices: set[int],
    stats: MergeStats,
) -> list[str]:
    block_matches = [match for match in matches if block.start <= match.source_index < block.end]
    prev_match = max((match for match in matches if match.source_index < block.start), default=None, key=lambda m: m.source_index)
    next_match = min((match for match in matches if match.source_index >= block.end), default=None, key=lambda m: m.source_index)
    source_window = surrounding_source_window(block, source_lines, prev_match, next_match)
    live_window = surrounding_live_window(live_lines, prev_match, next_match)

    if block_matches and can_replace_whole_block(
        block,
        source_lines,
        source_window,
        matched_source_indices,
    ):
        stats.whole_block_replacements += 1
        return live_lines[live_window.start:live_window.end]

    if can_replace_control_bounded_block(
        block,
        prev_match,
        next_match,
        live_window,
        source_lines,
    ):
        stats.whole_block_replacements += 1
        return live_lines[live_window.start:live_window.end]

    if can_replace_plain_window_block(
        block,
        source_window,
        live_window,
        source_lines,
    ):
        stats.whole_block_replacements += 1
        return live_lines[live_window.start:live_window.end]

    if len(block_matches) >= 2:
        stats.partial_block_merges += 1
        return merge_block_between_matches(block, source_lines, live_lines, block_matches)

    if len(block_matches) == 1:
        source_index = block_matches[0].source_index
        live_index = block_matches[0].live_index
        replacement = [source_lines[index].text for index in range(block.start, block.end)]
        replacement[source_index - block.start] = live_lines[live_index]
        stats.partial_block_merges += 1
        return replacement

    stats.unchanged_blocks += 1
    return [source_lines[index].text for index in range(block.start, block.end)]


def can_replace_whole_block(
    block: BlockRange,
    source_lines: list[SourceLine],
    source_window: BlockRange,
    matched_source_indices: set[int],
) -> bool:
    if source_window.start == 0 or source_window.end == len(source_lines):
        return False

    seen_block_line = False
    for index in range(source_window.start, source_window.end):
        if block.start <= index < block.end:
            seen_block_line = True
            continue
        if source_lines[index].kind == "control":
            continue
        if source_lines[index].kind != "literal":
            return False
        if index in matched_source_indices:
            return False

    return seen_block_line


def can_replace_control_bounded_block(
    block: BlockRange,
    prev_match: MatchPair | None,
    next_match: MatchPair | None,
    live_window: BlockRange,
    source_lines: list[SourceLine],
) -> bool:
    if prev_match is None or next_match is None:
        return False

    if live_window.start >= live_window.end:
        return False

    if not is_control_bounded_block(block, source_lines):
        return False

    previous_control = source_lines[block.start - 1].text.rstrip("\n")
    next_control = source_lines[block.end].text.rstrip("\n")
    if is_branching_control_line(previous_control) or is_branching_control_line(next_control):
        return False

    return True


def can_replace_plain_window_block(
    block: BlockRange,
    source_window: BlockRange,
    live_window: BlockRange,
    source_lines: list[SourceLine],
) -> bool:
    if live_window.start >= live_window.end:
        return False

    if source_window.start != block.start or source_window.end != block.end:
        return False

    return not any(
        source_lines[index].kind == "control"
        for index in range(source_window.start, source_window.end)
    )


def is_control_bounded_block(block: BlockRange, source_lines: list[SourceLine]) -> bool:
    if block.start == 0 or block.end >= len(source_lines):
        return False

    if source_lines[block.start - 1].kind != "control":
        return False

    if source_lines[block.end].kind != "control":
        return False

    return True


def is_branching_control_line(line: str) -> bool:
    normalized_line = line.strip()
    return normalized_line.startswith("{%@@ elif ") or normalized_line.startswith("{%@@ else ")


def surrounding_source_window(
    block: BlockRange,
    source_lines: list[SourceLine],
    prev_match: MatchPair | None,
    next_match: MatchPair | None,
) -> BlockRange:
    start = 0 if prev_match is None else prev_match.source_index + 1
    end = len(source_lines) if next_match is None else next_match.source_index
    return BlockRange(start, end)


def surrounding_live_window(
    live_lines: list[str],
    prev_match: MatchPair | None,
    next_match: MatchPair | None,
) -> BlockRange:
    start = 0 if prev_match is None else prev_match.live_index + 1
    end = len(live_lines) if next_match is None else next_match.live_index
    return BlockRange(start, end)


def merge_block_between_matches(
    block: BlockRange,
    source_lines: list[SourceLine],
    live_lines: list[str],
    block_matches: list[MatchPair],
) -> list[str]:
    merged_lines: list[str] = []
    first_match = block_matches[0]
    merged_lines.extend(source_lines[index].text for index in range(block.start, first_match.source_index))
    merged_lines.append(live_lines[first_match.live_index])

    previous_match = first_match
    for current_match in block_matches[1:]:
        merged_lines.extend(live_lines[index] for index in range(previous_match.live_index + 1, current_match.live_index))
        merged_lines.append(live_lines[current_match.live_index])
        previous_match = current_match

    merged_lines.extend(source_lines[index].text for index in range(previous_match.source_index + 1, block.end))
    return merged_lines


def merge_template(template_lines: list[str], live_lines: list[str]) -> tuple[list[str], MergeStats]:
    source_lines = build_source_lines(template_lines)
    matches = align_source_to_live(source_lines, live_lines)
    matched_source_indices = {match.source_index for match in matches}
    stats = MergeStats(matched_lines=len(matches))

    literal_blocks = find_literal_blocks(source_lines)
    merged_output: list[str] = []
    block_iter = iter(literal_blocks)
    current_block = next(block_iter, None)
    line_index = 0

    while line_index < len(source_lines):
        if current_block is not None and line_index == current_block.start:
            merged_output.extend(
                merge_literal_block(
                    current_block,
                    source_lines,
                    live_lines,
                    matches,
                    matched_source_indices,
                    stats,
                )
            )
            line_index = current_block.end
            current_block = next(block_iter, None)
            continue

        source_line = source_lines[line_index]
        merged_output.append(source_line.text)
        line_index += 1

    return merged_output, stats


def sync_mode(path: Path, reference_path: Path) -> None:
    if not path.exists() or not reference_path.exists():
        return

    reference_mode = reference_path.stat().st_mode & 0o777
    current_mode = path.stat().st_mode & 0o777
    if current_mode != reference_mode:
        path.chmod(reference_mode)


def write_output(content: str, template_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    sync_mode(output_path, template_path)


def main() -> int:
    args = parse_args()
    template_path = args.template_path
    live_path = args.live_path

    if args.in_place and args.output_path is not None:
        raise ValueError("use either --in-place or output_path, not both")

    if args.in_place or args.output_path is None:
        output_path = template_path
    else:
        output_path = args.output_path

    template_lines = load_lines(template_path)
    live_lines = load_lines(live_path)
    merged_lines, stats = merge_template(template_lines, live_lines)
    merged_content = "".join(merged_lines)

    if args.dry_run:
        print(merged_content, end="")
        return 0

    write_output(merged_content, template_path, output_path)
    print(
        "merged template update:"
        f" matched_lines={stats.matched_lines}"
        f" whole_blocks={stats.whole_block_replacements}"
        f" partial_blocks={stats.partial_block_merges}"
        f" unchanged_blocks={stats.unchanged_blocks}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

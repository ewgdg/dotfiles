#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import tomlkit
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument


TomlContainer = TOMLDocument | Table


DEFAULT_MANAGER_VALUES: tuple[tuple[tuple[str, str], object], ...] = (
    (("ui", "compact_path_tail_segments"), 3),
    (("symlinks", "file_symlink_mode"), "prompt"),
    (("symlinks", "dir_symlink_mode"), "follow"),
)


def load_config(config_path: Path) -> TOMLDocument:
    if not config_path.exists():
        return tomlkit.document()
    return tomlkit.parse(config_path.read_text(encoding="utf-8"))


def has_key_path(doc: TomlContainer, key_path: tuple[str, ...]) -> bool:
    current: object = doc
    for key in key_path:
        if not isinstance(current, (TOMLDocument, Table)) or key not in current:
            return False
        current = current[key]
    return True


def ensure_table(doc: TOMLDocument, table_name: str) -> Table:
    existing = doc.get(table_name)
    if isinstance(existing, Table):
        return existing
    table = tomlkit.table()
    doc[table_name] = table
    return table


def add_default_if_missing(
    base_doc: TOMLDocument,
    overlay_doc: TOMLDocument,
    key_path: tuple[str, str],
    value: object,
) -> None:
    if has_key_path(base_doc, key_path):
        return
    table = ensure_table(overlay_doc, key_path[0])
    table.add(key_path[1], value)


def build_overlay(config_path: Path, repo_name: str, repo_root: str) -> TOMLDocument:
    base_doc = load_config(config_path)

    repo_config = tomlkit.table()
    repo_config.add("path", repo_root)
    repo_config.add("order", 10)
    repo_config.add("state_key", repo_name)

    repos_config = tomlkit.table()
    repos_config.add(repo_name, repo_config)

    doc = tomlkit.document()
    doc.add("repos", repos_config)

    # Defaults mirror this repo owner's current dotman manager preferences, but
    # are emitted only for missing keys so existing machine-local choices win.
    for key_path, value in DEFAULT_MANAGER_VALUES:
        add_default_if_missing(base_doc, doc, key_path, value)

    return doc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate dotman manager config overlay for this dotfiles repo."
    )
    parser.add_argument("--config-path", required=True, type=Path)
    parser.add_argument("--output-path", required=True, type=Path)
    parser.add_argument("--repo-name", required=True)
    parser.add_argument("--repo-root", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    overlay_doc = build_overlay(args.config_path, args.repo_name, args.repo_root)
    args.output_path.write_text(overlay_doc.as_string(), encoding="utf-8")


if __name__ == "__main__":
    main()

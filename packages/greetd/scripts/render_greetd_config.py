#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
from pathlib import Path
import sys
import tomllib
from typing import Any, Iterable, Sequence

import tomlkit


_AUTOLOGIN_PLACEHOLDER = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
_HOST_USER_PLACEHOLDER = "__PLACEHOLDER_GREETD_HOST_USER__"
_DEFAULT_WAYLAND_SESSION_DIRS = (
    Path("/usr/local/share/wayland-sessions"),
    Path("/usr/share/wayland-sessions"),
)
_DEFAULT_XSESSION_DIRS = (
    Path("/usr/local/share/xsessions"),
    Path("/usr/share/xsessions"),
)


def resolve_session_desktop_path(
    session_name: str,
    *,
    wayland_session_dirs: Sequence[Path],
    xsession_dirs: Sequence[Path],
) -> Path:
    candidate_paths = [
        *(session_dir / f"{session_name}.desktop" for session_dir in wayland_session_dirs),
        *(session_dir / f"{session_name}.desktop" for session_dir in xsession_dirs),
    ]

    for candidate_path in candidate_paths:
        if candidate_path.is_file():
            return candidate_path

    searched_paths = "\n  - ".join(str(path) for path in candidate_paths)
    raise FileNotFoundError(
        f"unable to find {session_name}.desktop in session directories:\n  - {searched_paths}"
    )


def read_desktop_entry_exec(desktop_entry_path: Path) -> str:
    desktop_entry = configparser.RawConfigParser(interpolation=None, strict=False)
    desktop_entry.optionxform = str

    with desktop_entry_path.open("r", encoding="utf-8") as handle:
        desktop_entry.read_file(handle)

    section_name = "Desktop Entry"
    option_name = "Exec"
    if not desktop_entry.has_section(section_name):
        raise ValueError(f"desktop entry missing [{section_name}] section: {desktop_entry_path}")
    if not desktop_entry.has_option(section_name, option_name):
        raise ValueError(f"desktop entry missing {option_name}= line: {desktop_entry_path}")

    exec_command = desktop_entry.get(section_name, option_name, raw=True).strip()
    if not exec_command:
        raise ValueError(f"desktop entry has empty {option_name}= line: {desktop_entry_path}")

    return exec_command

def collect_placeholder_paths(
    value: Any,
    replacements: dict[str, str],
    path: tuple[Any, ...] = (),
) -> Iterable[tuple[tuple[Any, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from collect_placeholder_paths(child, replacements, (*path, key))
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from collect_placeholder_paths(child, replacements, (*path, index))
        return

    if isinstance(value, str) and value in replacements:
        yield path, replacements[value]


def collect_missing_placeholders(
    value: Any,
    *,
    placeholder_prefix: str,
    replacements: dict[str, str],
) -> list[str]:
    missing: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for child in node.values():
                visit(child)
            return
        if isinstance(node, list):
            for child in node:
                visit(child)
            return
        if isinstance(node, str) and node.startswith(placeholder_prefix) and node not in replacements:
            missing.add(node)

    visit(value)
    return sorted(missing)


def assign_path(target: Any, path: tuple[Any, ...], value: str) -> None:
    cursor = target
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def render_greetd_config(template_text: str, *, replacements: dict[str, str], placeholder_prefix: str) -> str:
    template_data = tomllib.loads(template_text)
    missing_placeholders = collect_missing_placeholders(
        template_data,
        placeholder_prefix=placeholder_prefix,
        replacements=replacements,
    )
    if missing_placeholders:
        joined = ", ".join(missing_placeholders)
        raise ValueError(f"template has unresolved placeholders: {joined}")

    rendered_document = tomlkit.parse(template_text)
    for path, replacement_value in collect_placeholder_paths(template_data, replacements):
        assign_path(rendered_document, path, replacement_value)

    rendered_text = tomlkit.dumps(rendered_document)
    tomllib.loads(rendered_text)
    return rendered_text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render greetd config with explicit greetd placeholder replacements."
    )
    parser.add_argument("template_path", type=Path, help="Path to greetd config template.")
    parser.add_argument("--session", required=True, help="Session desktop entry stem, without .desktop.")
    parser.add_argument("--host-user", required=True, help="User for [initial_session].user.")
    parser.add_argument(
        "--placeholder-prefix",
        default="__PLACEHOLDER_",
        help="Prefix used to detect unresolved placeholder values.",
    )
    parser.add_argument(
        "--wayland-sessions-dir",
        action="append",
        dest="wayland_session_dirs",
        type=Path,
        help="Additional Wayland session directory to search. Can be passed more than once.",
    )
    parser.add_argument(
        "--xsession-dir",
        action="append",
        dest="xsession_dirs",
        type=Path,
        help="Additional X11 session directory to search. Can be passed more than once.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    wayland_session_dirs = tuple(args.wayland_session_dirs or _DEFAULT_WAYLAND_SESSION_DIRS)
    xsession_dirs = tuple(args.xsession_dirs or _DEFAULT_XSESSION_DIRS)

    try:
        template_text = args.template_path.read_text(encoding="utf-8")
        desktop_entry_path = resolve_session_desktop_path(
            args.session,
            wayland_session_dirs=wayland_session_dirs,
            xsession_dirs=xsession_dirs,
        )
        replacements = {
            _AUTOLOGIN_PLACEHOLDER: read_desktop_entry_exec(desktop_entry_path),
            _HOST_USER_PLACEHOLDER: args.host_user,
        }
        rendered_text = render_greetd_config(
            template_text,
            replacements=replacements,
            placeholder_prefix=args.placeholder_prefix,
        )
    except Exception as exc:
        print(f"render_greetd_config: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(rendered_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

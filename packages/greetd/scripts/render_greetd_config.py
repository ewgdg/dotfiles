#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import sys
import tomllib
from typing import Any, Iterable, Sequence

import tomlkit


_AUTOLOGIN_PLACEHOLDER = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
_HOST_USER_PLACEHOLDER = "__PLACEHOLDER_GREETD_HOST_USER__"
_DEFAULT_SESSION_LAUNCHER = "/usr/local/bin/greetd-start-session"


def resolve_session_command(
    session_name: str,
    *,
    session_command: str | None,
    session_launcher: str,
) -> str:
    if session_command is not None and session_command.strip():
        return session_command.strip()

    # Keep render repo-pure. Desktop entries may be installed by pre_push hooks in
    # the same dotman run, so resolve their Exec= line at greetd login time.
    return f"{session_launcher} {shlex.quote(session_name)}"


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
    parser.add_argument(
        "--session-command",
        help="Explicit command for [initial_session].command. When set, skips runtime .desktop Exec lookup.",
    )
    parser.add_argument(
        "--session-launcher",
        default=_DEFAULT_SESSION_LAUNCHER,
        help="Runtime helper used to resolve session .desktop Exec lines when --session-command is unset.",
    )
    parser.add_argument("--host-user", required=True, help="User for [initial_session].user.")
    parser.add_argument(
        "--placeholder-prefix",
        default="__PLACEHOLDER_",
        help="Prefix used to detect unresolved placeholder values.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        template_text = args.template_path.read_text(encoding="utf-8")
        session_command = resolve_session_command(
            args.session,
            session_command=args.session_command,
            session_launcher=args.session_launcher,
        )
        replacements = {
            _AUTOLOGIN_PLACEHOLDER: session_command,
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

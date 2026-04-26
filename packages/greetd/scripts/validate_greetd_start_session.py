#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Sequence


_DEFAULT_SESSION_DIRS = (
    Path("/usr/local/share/wayland-sessions"),
    Path("/usr/share/wayland-sessions"),
    Path("/usr/local/share/xsessions"),
    Path("/usr/share/xsessions"),
)


def resolve_session_desktop_path(session_name: str, *, session_dirs: Sequence[Path]) -> Path:
    candidate_paths = [session_dir / f"{session_name}.desktop" for session_dir in session_dirs]
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


def parse_supported_exec_argv(exec_command: str) -> list[str]:
    if "%" in exec_command.replace("%%", ""):
        raise ValueError("session Exec= contains unsupported desktop field code")
    try:
        return shlex.split(exec_command.replace("%%", "%"), posix=True)
    except ValueError as exc:
        raise ValueError(f"session Exec= is not supported by greetd-start-session: {exc}") from exc


def run_helper_argv(helper: Path, session_name: str, *, session_dirs: Sequence[Path]) -> list[str]:
    env = os.environ.copy()
    env["GREETD_START_SESSION_DIRS"] = ":".join(str(path) for path in session_dirs)
    completed = subprocess.run(
        ["sh", str(helper), "--print-argv", session_name],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or f"helper exited with status {completed.returncode}")
    return completed.stdout.splitlines()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate greetd runtime session launcher support.")
    parser.add_argument("--session", required=True, help="Session desktop entry stem, without .desktop.")
    parser.add_argument(
        "--session-command",
        help="Explicit [initial_session].command. When set, .desktop helper validation is skipped.",
    )
    parser.add_argument("--helper", required=True, type=Path, help="Path to greetd-start-session helper to validate.")
    parser.add_argument(
        "--session-dir",
        action="append",
        dest="session_dirs",
        type=Path,
        help="Session directory to search. Can be passed more than once. Defaults to system session dirs.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session_dirs = tuple(args.session_dirs or _DEFAULT_SESSION_DIRS)

    try:
        if args.session_command is not None and args.session_command.strip():
            shlex.split(args.session_command)
            return 0

        syntax_check = subprocess.run(["sh", "-n", str(args.helper)], capture_output=True, text=True, check=False)
        if syntax_check.returncode != 0:
            raise ValueError(syntax_check.stderr.strip() or "helper shell syntax check failed")

        desktop_entry_path = resolve_session_desktop_path(args.session, session_dirs=session_dirs)
        exec_command = read_desktop_entry_exec(desktop_entry_path)
        expected_argv = parse_supported_exec_argv(exec_command)
        helper_argv = run_helper_argv(args.helper, args.session, session_dirs=session_dirs)
        if helper_argv != expected_argv:
            raise ValueError(
                "helper argv mismatch for "
                f"{desktop_entry_path}: expected {expected_argv!r}, got {helper_argv!r}"
            )
    except Exception as exc:
        print(f"validate_greetd_start_session: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

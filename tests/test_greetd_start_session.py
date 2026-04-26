from __future__ import annotations

from pathlib import Path
import os
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "packages/greetd/files/usr/local/bin/greetd-start-session"
VALIDATOR_PATH = REPO_ROOT / "packages/greetd/scripts/validate_greetd_start_session.py"


def write_desktop_entry(session_dir: Path, name: str, exec_line: str) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"{name}.desktop").write_text(
        f"""
[Desktop Entry]
Name={name}
Exec={exec_line}
Type=Application
""".lstrip(),
        encoding="utf-8",
    )


def run_helper(tmp_path: Path, session_dir: Path, session_name: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GREETD_START_SESSION_DIRS"] = str(session_dir)
    return subprocess.run(
        ["sh", str(HELPER_PATH), "--print-argv", session_name],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_greetd_start_session_prints_parsed_session_exec_argv(tmp_path: Path) -> None:
    session_dir = tmp_path / "wayland-sessions"
    write_desktop_entry(session_dir, "niri", '/usr/bin/env FOO="bar baz" niri-session --flag')

    completed = run_helper(tmp_path, session_dir, "niri")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == ["/usr/bin/env", "FOO=bar baz", "niri-session", "--flag"]


def test_greetd_start_session_rejects_desktop_field_codes(tmp_path: Path) -> None:
    session_dir = tmp_path / "wayland-sessions"
    write_desktop_entry(session_dir, "bad", "session %f")

    completed = run_helper(tmp_path, session_dir, "bad")

    assert completed.returncode == 1
    assert "unsupported field code" in completed.stderr


def test_validate_greetd_start_session_compares_helper_with_python_parser(tmp_path: Path) -> None:
    session_dir = tmp_path / "wayland-sessions"
    write_desktop_entry(session_dir, "cosmic", "/usr/bin/start-cosmic")

    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            str(VALIDATOR_PATH),
            "--session",
            "cosmic",
            "--helper",
            str(HELPER_PATH),
            "--session-dir",
            str(session_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

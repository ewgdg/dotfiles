from __future__ import annotations

from pathlib import Path
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "packages/greetd/scripts/render_greetd_config.py"


def run_render(
    tmp_path: Path,
    template_path: Path,
    session_name: str,
    *,
    host_user: str = "xian",
    session_command: str | None = None,
    session_launcher: str = "/usr/local/bin/greetd-start-session",
) -> subprocess.CompletedProcess[str]:
    command = [
        "uv",
        "run",
        "--project",
        str(REPO_ROOT),
        str(SCRIPT_PATH),
        str(template_path),
        "--session",
        session_name,
        "--session-launcher",
        session_launcher,
        "--host-user",
        host_user,
        "--placeholder-prefix",
        "__PLACEHOLDER_",
    ]

    if session_command is not None:
        command.extend(["--session-command", session_command])

    return subprocess.run(
        command,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_render_greetd_config_replaces_placeholder_values(tmp_path: Path) -> None:
    template_path = tmp_path / "config.toml"
    template_path.write_text(
        """
[terminal]
vt = 1

[initial_session]
command = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
user = "__PLACEHOLDER_GREETD_HOST_USER__"

[default_session]
command = "tuigreet"
user = "greeter"
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_render(
        tmp_path,
        template_path,
        "niri",
        host_user="xian",
    )

    assert completed.returncode == 0, completed.stderr

    rendered = tomllib.loads(completed.stdout)
    assert rendered["initial_session"]["command"] == "env AUTOLOGIN_SESSION=1 /usr/local/bin/greetd-start-session niri"
    assert rendered["initial_session"]["user"] == "xian"
    assert rendered["default_session"]["command"] == "tuigreet"


def test_render_greetd_config_uses_explicit_session_command(tmp_path: Path) -> None:
    template_path = tmp_path / "config.toml"
    template_path.write_text(
        """
[initial_session]
command = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
user = "__PLACEHOLDER_GREETD_HOST_USER__"
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_render(
        tmp_path,
        template_path,
        "sway",
        session_command="/usr/local/bin/start-sway",
    )

    assert completed.returncode == 0, completed.stderr
    rendered = tomllib.loads(completed.stdout)
    assert rendered["initial_session"]["command"] == "env AUTOLOGIN_SESSION=1 /usr/local/bin/start-sway"
    assert rendered["initial_session"]["user"] == "xian"


def test_render_greetd_config_errors_when_placeholder_is_unresolved(tmp_path: Path) -> None:
    template_path = tmp_path / "config.toml"
    template_path.write_text(
        """
[initial_session]
command = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
user = "__PLACEHOLDER_GREETD_HOST_USER__"
extra = "__PLACEHOLDER_MISSING__"
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_render(tmp_path, template_path, "niri")

    assert completed.returncode == 1
    assert "__PLACEHOLDER_MISSING__" in completed.stderr


def test_render_greetd_config_does_not_require_session_desktop_at_render_time(tmp_path: Path) -> None:
    template_path = tmp_path / "config.toml"
    template_path.write_text(
        """
[initial_session]
command = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
user = "__PLACEHOLDER_GREETD_HOST_USER__"
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_render(tmp_path, template_path, "missing-session")

    assert completed.returncode == 0, completed.stderr
    rendered = tomllib.loads(completed.stdout)
    assert rendered["initial_session"]["command"] == (
        "env AUTOLOGIN_SESSION=1 /usr/local/bin/greetd-start-session missing-session"
    )

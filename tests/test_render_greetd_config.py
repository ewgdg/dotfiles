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
    wayland_sessions_dir: Path | None = None,
    xsessions_dir: Path | None = None,
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
        "--host-user",
        host_user,
        "--placeholder-prefix",
        "__PLACEHOLDER_",
    ]

    if wayland_sessions_dir is not None:
        command.extend(["--wayland-sessions-dir", str(wayland_sessions_dir)])

    if xsessions_dir is not None:
        command.extend(["--xsession-dir", str(xsessions_dir)])

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

    wayland_sessions_dir = tmp_path / "wayland-sessions"
    wayland_sessions_dir.mkdir()
    (wayland_sessions_dir / "niri.desktop").write_text(
        """
[Desktop Entry]
Name=Niri
Exec=/usr/bin/env FOO="bar baz" niri-session --flag
Type=Application
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_render(
        tmp_path,
        template_path,
        "niri",
        host_user="xian",
        wayland_sessions_dir=wayland_sessions_dir,
    )

    assert completed.returncode == 0, completed.stderr

    rendered = tomllib.loads(completed.stdout)
    assert rendered["initial_session"]["command"] == '/usr/bin/env FOO="bar baz" niri-session --flag'
    assert rendered["initial_session"]["user"] == "xian"
    assert rendered["default_session"]["command"] == "tuigreet"


def test_render_greetd_config_falls_back_to_xsessions(tmp_path: Path) -> None:
    template_path = tmp_path / "config.toml"
    template_path.write_text(
        """
[initial_session]
command = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
user = "__PLACEHOLDER_GREETD_HOST_USER__"
""".lstrip(),
        encoding="utf-8",
    )

    xsessions_dir = tmp_path / "xsessions"
    xsessions_dir.mkdir()
    (xsessions_dir / "plasmax11.desktop").write_text(
        """
[Desktop Entry]
Name=Plasma (X11)
Exec=/usr/bin/startplasma-x11
Type=Application
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_render(
        tmp_path,
        template_path,
        "plasmax11",
        xsessions_dir=xsessions_dir,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = tomllib.loads(completed.stdout)
    assert rendered["initial_session"]["command"] == "/usr/bin/startplasma-x11"
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

    wayland_sessions_dir = tmp_path / "wayland-sessions"
    wayland_sessions_dir.mkdir()
    (wayland_sessions_dir / "niri.desktop").write_text(
        """
[Desktop Entry]
Name=Niri
Exec=niri-session
Type=Application
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_render(
        tmp_path,
        template_path,
        "niri",
        wayland_sessions_dir=wayland_sessions_dir,
    )

    assert completed.returncode == 1
    assert "__PLACEHOLDER_MISSING__" in completed.stderr


def test_render_greetd_config_errors_when_session_desktop_is_missing(tmp_path: Path) -> None:
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

    assert completed.returncode == 1
    assert "missing-session.desktop" in completed.stderr

from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "packages/greetd/scripts/capture_greetd_config.py"


def run_capture(tmp_path: Path, live_path: Path, template_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            str(SCRIPT_PATH),
            str(live_path),
            "--template-file",
            str(template_path),
            "--placeholder-prefix",
            "__PLACEHOLDER_",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_capture_greetd_config_restores_placeholder_fields(tmp_path: Path) -> None:
    template_path = tmp_path / "template.toml"
    template_path.write_text(
        """
[terminal]
vt = 1

[general]
source_profile = true

[default_session]
command = "tuigreet"
user = "greeter"

[initial_session]
command = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"
user = "__PLACEHOLDER_GREETD_HOST_USER__"
""".lstrip(),
        encoding="utf-8",
    )

    live_path = tmp_path / "live.toml"
    live_path.write_text(
        """
[terminal]
vt = 2

[general]
source_profile = false

[default_session]
command = "tuigreet"
user = "greeter"

[initial_session]
command = "niri-session"
user = "xian"
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_capture(tmp_path, live_path, template_path)

    assert completed.returncode == 0, completed.stderr
    assert 'command = "__PLACEHOLDER_GREETD_AUTOLOGIN_COMMAND__"' in completed.stdout
    assert 'user = "__PLACEHOLDER_GREETD_HOST_USER__"' in completed.stdout
    # Non-placeholder live values should still pull back into repo.
    assert 'vt = 2' in completed.stdout
    assert 'source_profile = false' in completed.stdout


def test_capture_greetd_config_errors_when_template_has_no_placeholders(tmp_path: Path) -> None:
    template_path = tmp_path / "template.toml"
    template_path.write_text(
        """
[initial_session]
command = "niri-session"
user = "xian"
""".lstrip(),
        encoding="utf-8",
    )

    live_path = tmp_path / "live.toml"
    live_path.write_text(
        """
[initial_session]
command = "niri-session"
user = "xian"
""".lstrip(),
        encoding="utf-8",
    )

    completed = run_capture(tmp_path, live_path, template_path)

    assert completed.returncode == 1
    assert "__PLACEHOLDER_" in completed.stderr

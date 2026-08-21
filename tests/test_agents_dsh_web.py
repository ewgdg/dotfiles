from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
DSH_LAUNCHER = (
    REPO_ROOT / "packages/linux/deepseek-harness/files/local/bin/dsh"
)
AGENTS_ZSH = REPO_ROOT / "packages/shell/files/config/zsh/agents.zsh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def configure_global_dsh(tmp_path: Path, content: str) -> Path:
    npm_prefix = tmp_path / "npm-prefix"
    npm_bin = npm_prefix / "bin"
    npm_bin.mkdir(parents=True)
    write_executable(npm_bin / "dsh", content)
    write_executable(
        tmp_path / "bin/npm",
        """#!/bin/sh
if [ "$*" = "prefix --global" ]; then
  printf '%s\n' "$TEST_NPM_PREFIX"
  exit 0
fi
exit 2
""",
    )
    return npm_prefix


def test_dsh_runs_installed_release_and_opens_dedicated_app_when_ready(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"

    write_executable(
        bin_dir / "curl",
        """#!/bin/sh
printf '%s\n' '<script>window.__DSH_BOOT__ = {};</script>'
""",
    )
    write_executable(
        bin_dir / "google-chrome-stable",
        """#!/bin/sh
printf 'google-chrome-stable %s\n' "$*" >> "$TEST_COMMAND_LOG"
""",
    )
    npm_prefix = configure_global_dsh(
        tmp_path,
        """#!/bin/sh
printf 'dsh %s\n' "$*" >> "$TEST_COMMAND_LOG"
sleep 0.2
exit 23
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "TEST_COMMAND_LOG": str(command_log),
            "TEST_NPM_PREFIX": str(npm_prefix),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        }
    )

    completed = subprocess.run(
        ["sh", str(DSH_LAUNCHER)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 23
    assert set(command_log.read_text(encoding="utf-8").splitlines()) == {
        "dsh web --host 127.0.0.1 --port 3080 --no-open",
        " ".join(
            [
                "google-chrome-stable",
                f"--user-data-dir={tmp_path / 'state/deepseek-harness/chrome'}",
                "--class=deepseek-harness",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-mode",
                "--disable-features=TranslateUI",
                "--new-window",
                "http://127.0.0.1:3080",
            ]
        ),
    }


def test_app_mode_stops_dsh_when_its_chrome_window_closes(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"

    write_executable(
        bin_dir / "curl",
        """#!/bin/sh
printf '%s\n' '<script>window.__DSH_BOOT__ = {};</script>'
""",
    )
    write_executable(
        bin_dir / "google-chrome-stable",
        """#!/bin/sh
printf 'google-chrome-stable %s\n' "$*" >> "$TEST_COMMAND_LOG"
sleep 0.15
""",
    )
    npm_prefix = configure_global_dsh(
        tmp_path,
        """#!/bin/sh
printf 'dsh %s\n' "$*" >> "$TEST_COMMAND_LOG"
trap 'printf "dsh stopped\\n" >> "$TEST_COMMAND_LOG"; exit 0' TERM
sleep 1
printf 'dsh finished\n' >> "$TEST_COMMAND_LOG"
exit 19
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "TEST_COMMAND_LOG": str(command_log),
            "TEST_NPM_PREFIX": str(npm_prefix),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        }
    )

    started_at = time.monotonic()
    completed = subprocess.run(
        ["sh", str(DSH_LAUNCHER), "--app"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=3,
    )

    assert completed.returncode == 0
    assert time.monotonic() - started_at < 0.8
    assert "dsh stopped" in command_log.read_text(encoding="utf-8").splitlines()


def test_second_app_launch_focuses_the_existing_chrome_instance(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"
    close_browser = tmp_path / "close-browser"

    write_executable(
        bin_dir / "curl",
        """#!/bin/sh
printf '%s\n' '<script>window.__DSH_BOOT__ = {};</script>'
""",
    )
    write_executable(
        bin_dir / "google-chrome-stable",
        """#!/bin/sh
profile_dir=
focus_url=
result_file=
for argument in "$@"; do
  case "$argument" in
    --user-data-dir=*) profile_dir=${argument#*=} ;;
    --focus=*) focus_url=${argument#*=} ;;
    --focus-result-file=*) result_file=${argument#*=} ;;
  esac
done
if [ -n "$focus_url" ]; then
  printf 'chrome focus %s\n' "$focus_url" >> "$TEST_COMMAND_LOG"
  printf '%s\n' '{"exit_code":0,"status":"focused"}' > "$result_file"
  exit 0
fi
printf 'chrome window\n' >> "$TEST_COMMAND_LOG"
ln -s "test-host-$$" "$profile_dir/SingletonLock"
while [ ! -f "$TEST_CLOSE_BROWSER" ]; do sleep 0.02; done
""",
    )
    npm_prefix = configure_global_dsh(
        tmp_path,
        """#!/bin/sh
printf 'dsh server\n' >> "$TEST_COMMAND_LOG"
trap 'exit 0' TERM
while :; do sleep 0.05; done
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "TEST_CLOSE_BROWSER": str(close_browser),
            "TEST_COMMAND_LOG": str(command_log),
            "TEST_NPM_PREFIX": str(npm_prefix),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        }
    )

    first_launch = subprocess.Popen(
        ["sh", str(DSH_LAUNCHER), "--app"],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if command_log.exists() and "chrome window" in command_log.read_text(
            encoding="utf-8"
        ):
            break
        time.sleep(0.02)
    else:
        first_launch.terminate()
        first_launch.wait(timeout=1)
        raise AssertionError("first Chrome window did not start")

    second_launch = subprocess.run(
        ["sh", str(DSH_LAUNCHER), "--app"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=2,
    )

    close_browser.touch()
    first_launch.wait(timeout=2)
    commands = command_log.read_text(encoding="utf-8").splitlines()
    assert second_launch.returncode == 0
    assert commands.count("dsh server") == 1
    assert commands.count("chrome window") == 1
    assert commands.count("chrome focus http://127.0.0.1:3080") == 1


def test_shell_uses_dsh_executable_without_shadowing_it(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(bin_dir / "dsh", "#!/bin/sh\n")

    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    completed = subprocess.run(
        ["zsh", "-fc", f"source {AGENTS_ZSH}; whence -w dsh"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "dsh: command"

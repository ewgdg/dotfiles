from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import os


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "packages/shell/scripts/core_env_token.sh"
CORE_ENV_PATH = REPO_ROOT / "packages/shell/files/env.core.sh"
CORE_ENV_TEXT = CORE_ENV_PATH.read_text(encoding="utf-8")
CORE_ENV_TOKEN = f"sha256:{hashlib.sha256(CORE_ENV_PATH.read_bytes()).hexdigest()}"
MANAGED_BEGIN = "# dotman: begin managed core env token"
MANAGED_END = "# dotman: end managed core env token"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_print_outputs_repo_core_env_token() -> None:
    completed = run_script("print", str(CORE_ENV_PATH))

    assert completed.returncode == 0
    assert completed.stdout.strip() == CORE_ENV_TOKEN
    assert completed.stderr == ""


def test_render_appends_managed_token_block() -> None:
    completed = run_script("render", str(CORE_ENV_PATH))

    assert completed.returncode == 0
    assert completed.stdout.startswith(CORE_ENV_TEXT)
    assert MANAGED_BEGIN in completed.stdout
    assert f"export DOTFILES_ENV_CORE_SH_TOKEN='{CORE_ENV_TOKEN}'" in completed.stdout
    assert MANAGED_END in completed.stdout


def test_capture_strips_managed_token_block(tmp_path: Path) -> None:
    rendered_path = tmp_path / "env.core.sh"
    rendered_path.write_text(run_script("render", str(CORE_ENV_PATH)).stdout, encoding="utf-8")

    completed = run_script("capture", str(rendered_path))

    assert completed.returncode == 0
    assert completed.stdout == CORE_ENV_TEXT


def test_core_env_prepends_cargo_bin_on_clean_login_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cargo_bin = home / ".cargo/bin"
    cargo_bin.mkdir(parents=True)
    (home / ".local/bin").mkdir(parents=True)
    (home / "bin").mkdir()
    env = os.environ.copy()
    env.update({"HOME": str(home), "PATH": "/usr/bin:/bin"})

    completed = subprocess.run(
        ["sh", "-c", f'. "{CORE_ENV_PATH}"; printf "%s\\n" "$PATH"'],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    path_entries = completed.stdout.strip().split(":")
    assert path_entries.index(str(cargo_bin)) < path_entries.index("/usr/bin")
    assert path_entries.count(str(cargo_bin)) == 1


def test_core_env_exports_future_tool_paths_before_directories_exist(tmp_path: Path) -> None:
    home = tmp_path / "home"
    data_home = tmp_path / "data"
    env = os.environ.copy()
    for name in ("BUN_INSTALL", "GOPATH", "PNPM_HOME", "XDG_DATA_HOME"):
        env.pop(name, None)
    env.update(
        {"HOME": str(home), "XDG_DATA_HOME": str(data_home), "PATH": "/usr/bin:/bin"}
    )

    completed = subprocess.run(
        [
            "sh",
            "-c",
            f'. "{CORE_ENV_PATH}"; . "{CORE_ENV_PATH}"; printf "%s\\n%s\\n" "$GOPATH" "$PATH"',
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    go_path, path = completed.stdout.strip().splitlines()
    assert go_path == str(home / "go")

    path_entries = path.split(":")
    future_tool_paths = (
        home / "go/bin",
        home / ".bun/bin",
        home / ".npm/bin",
        home / ".cargo/bin",
        home / ".local/bin",
        home / "bin",
        data_home / "pnpm/bin",
    )
    for future_tool_path in future_tool_paths:
        assert path_entries.index(str(future_tool_path)) < path_entries.index("/usr/bin")
        assert path_entries.count(str(future_tool_path)) == 1


def test_core_env_uses_first_custom_gopath_for_installed_commands(tmp_path: Path) -> None:
    first_go_path = tmp_path / "primary-go"
    second_go_path = tmp_path / "secondary-go"
    custom_go_path = f"{first_go_path}:{second_go_path}"
    env = os.environ.copy()
    env.update({"GOPATH": custom_go_path, "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})

    completed = subprocess.run(
        [
            "sh",
            "-c",
            f'. "{CORE_ENV_PATH}"; printf "%s\\n%s\\n" "$GOPATH" "$PATH"',
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    go_path, path = completed.stdout.strip().splitlines()
    path_entries = path.split(":")
    assert go_path == custom_go_path
    assert str(first_go_path / "bin") in path_entries
    assert str(second_go_path / "bin") not in path_entries

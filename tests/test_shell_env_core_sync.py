from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess


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

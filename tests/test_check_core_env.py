from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/check_core_env.sh"
CORE_ENV_PATH = REPO_ROOT / "packages/shell/files/env.core.sh"
CORE_ENV_TOKEN = f"sha256:{hashlib.sha256(CORE_ENV_PATH.read_bytes()).hexdigest()}"


def run_check(*args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {
        "HOME": "/tmp/dotfiles-test-home",
        "PATH": os.environ["PATH"],
    }
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["sh", str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_check_core_env_accepts_loaded_core_env_token() -> None:
    completed = run_check(env_overrides={"DOTFILES_ENV_CORE_SH_TOKEN": CORE_ENV_TOKEN})

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_check_core_env_accepts_explicit_guard_bypass() -> None:
    completed = run_check(env_overrides={"DOTFILES_SKIP_CORE_ENV_GUARD": "1"})

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_check_core_env_rejects_stale_core_env_token() -> None:
    completed = run_check(env_overrides={"DOTFILES_ENV_CORE_SH_TOKEN": "sha256:stale"})

    assert completed.returncode == 100
    assert "repo core env not loaded or stale in current shell." in completed.stderr
    assert f'Run `. "{REPO_ROOT}/activate.sh"` then retry.' in completed.stderr
    assert "Or set `DOTFILES_SKIP_CORE_ENV_GUARD=1` to bypass this guard intentionally." in completed.stderr


def test_check_core_env_rejects_missing_core_env_token() -> None:
    completed = run_check()

    assert completed.returncode == 100
    assert "repo core env not loaded or stale in current shell." in completed.stderr

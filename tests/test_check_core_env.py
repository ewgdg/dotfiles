from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/check_core_env.sh"
CORE_ENV_SENTINEL = "dotfiles:packages/shell/files/env.core.sh"


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


def test_check_core_env_accepts_loaded_core_env_marker() -> None:
    completed = run_check(env_overrides={"DOTFILES_ENV_CORE_SH_LOADED": CORE_ENV_SENTINEL})

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_check_core_env_accepts_explicit_guard_bypass() -> None:
    completed = run_check(env_overrides={"DOTFILES_SKIP_CORE_ENV_GUARD": "1"})

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_check_core_env_skips_noninteractive_when_core_env_missing() -> None:
    completed = run_check()

    assert completed.returncode == 100
    assert "repo core env not loaded in current shell." in completed.stderr
    assert "Run `. ./activate.sh` then retry." in completed.stderr
    assert "Or set `DOTFILES_SKIP_CORE_ENV_GUARD=1` to bypass this guard intentionally." in completed.stderr

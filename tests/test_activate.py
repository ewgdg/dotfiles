from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ZSH = shutil.which("zsh")
CORE_ENV_PATH = REPO_ROOT / "packages/shell/files/env.core.sh"
CORE_ENV_TOKEN = f"sha256:{hashlib.sha256(CORE_ENV_PATH.read_bytes()).hexdigest()}"


@pytest.mark.skipif(ZSH is None, reason="zsh not installed")
def test_activate_does_not_enable_errexit_or_nounset_in_zsh() -> None:
    completed = subprocess.run(
        [
            ZSH,
            "-lc",
            "unsetopt errexit nounset; . ./activate.sh; printf '%s %s\n' \"$options[errexit]\" \"$options[nounset]\"",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "off off"


@pytest.mark.skipif(ZSH is None, reason="zsh not installed")
def test_activate_exports_core_env_token_in_zsh() -> None:
    completed = subprocess.run(
        [
            ZSH,
            "-lc",
            '. ./activate.sh; printf "%s\\n" "$DOTFILES_ENV_CORE_SH_TOKEN"',
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == CORE_ENV_TOKEN

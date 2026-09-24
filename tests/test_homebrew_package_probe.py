from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "scripts/probe_homebrew_packages_installed.sh"
INSTALL = REPO_ROOT / "scripts/install_homebrew_packages.sh"
WORK_NEEDED = 0
CURRENT = 100
BROKEN_BREW_ERROR = "Error: You have not agreed to the Xcode license."


def fake_brew(tmp_path: Path, *, installed: tuple[str, ...] = (), broken: bool = False) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    brew = bin_dir / "brew"
    if broken:
        body = f'echo "{BROKEN_BREW_ERROR}" >&2\nexit 1\n'
    else:
        # `brew list --formula|--cask --versions <name>`: missing exits 1 silently.
        body = (
            'if [ "$1" != list ]; then exit 1; fi\n'
            'shift 2\n'
            'name=${2:-}\n'
            f'for installed in {" ".join(installed)}; do\n'
            '  if [ -z "$name" ] || [ "$name" = "$installed" ]; then echo "$installed 1.0"; found=1; fi\n'
            'done\n'
            '[ -z "$name" ] || [ -n "${found:-}" ]\n'
        )
    brew.write_text("#!/bin/sh\n" + body)
    brew.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


def run(script: Path, env: dict[str, str], *packages: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", str(script), *packages], capture_output=True, text=True, env=env)


def test_probe_distinguishes_installed_from_missing_packages(tmp_path: Path) -> None:
    env = fake_brew(tmp_path, installed=("go",))

    assert run(PROBE, env, "go").returncode == CURRENT
    assert run(PROBE, env, "go", "node").returncode == WORK_NEEDED


def test_probe_fails_with_brew_error_instead_of_reporting_missing(tmp_path: Path) -> None:
    env = fake_brew(tmp_path, broken=True)

    completed = run(PROBE, env, "go")

    assert completed.returncode not in (WORK_NEEDED, CURRENT)
    assert BROKEN_BREW_ERROR in completed.stderr
    assert "missing" not in completed.stderr


def test_install_fails_with_brew_error_before_installing(tmp_path: Path) -> None:
    env = fake_brew(tmp_path, broken=True)

    completed = run(INSTALL, env, "go")

    assert completed.returncode != 0
    assert BROKEN_BREW_ERROR in completed.stderr

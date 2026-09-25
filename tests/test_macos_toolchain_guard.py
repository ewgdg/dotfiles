from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts/check_macos_toolchain.sh"


def fake_host(tmp_path: Path, *, system: str, clang_works: bool) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "uname": f"echo {system}",
        # Mirrors a broken Xcode: xcrun reports failure instead of running clang.
        "xcrun": "exit 0" if clang_works else "echo 'xcrun: error: unable to find utility \"clang\"' >&2; exit 72",
    }.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


def run_guard(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", str(GUARD)], capture_output=True, text=True, env=env)


def test_guard_passes_with_working_toolchain(tmp_path: Path) -> None:
    assert run_guard(fake_host(tmp_path, system="Darwin", clang_works=True)).returncode == 0


def test_guard_aborts_with_fix_when_toolchain_is_broken(tmp_path: Path) -> None:
    completed = run_guard(fake_host(tmp_path, system="Darwin", clang_works=False))

    # Guard exit 100 would silently drop push work; any other failure aborts planning.
    assert completed.returncode not in (0, 100)
    assert "xcode-select -s /Library/Developer/CommandLineTools" in completed.stderr


def test_guard_ignores_non_macos_hosts(tmp_path: Path) -> None:
    assert run_guard(fake_host(tmp_path, system="Linux", clang_works=False)).returncode == 0


def test_repo_guards_push_on_macos_toolchain() -> None:
    repo = tomllib.loads((REPO_ROOT / "repo.toml").read_text())

    assert 'sh "$DOTMAN_REPO_ROOT/scripts/check_macos_toolchain.sh"' in repo["hooks"]["guard_push"]

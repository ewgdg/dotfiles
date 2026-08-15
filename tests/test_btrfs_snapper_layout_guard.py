from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "packages/btrfs/snapper/scripts/has_supported_btrfs_layout.sh"


FAKE_FINDMNT_SCRIPT = """#!/usr/bin/env sh
set -eu

field=''
target=''

while [ "$#" -gt 0 ]; do
  case "$1" in
    -no)
      field="$2"
      shift 2
      ;;
    --target)
      target="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

case "$target:$field" in
  /:FSTYPE)
    printf '%s\\n' "${ROOT_FSTYPE:-}"
    ;;
  /:MAJ:MIN)
    printf '%s\\n' "${ROOT_MAJMIN:-}"
    ;;
  /home:FSTYPE)
    printf '%s\\n' "${HOME_FSTYPE:-}"
    ;;
  /home:MAJ:MIN)
    printf '%s\\n' "${HOME_MAJMIN:-}"
    ;;
  /:TARGET)
    printf '%s\\n' "${ROOT_TARGET:-}"
    ;;
  /home:TARGET)
    printf '%s\\n' "${HOME_TARGET:-}"
    ;;
  /:FSROOT)
    printf '%s\\n' "${ROOT_FSROOT:-}"
    ;;
  /home:FSROOT)
    printf '%s\\n' "${HOME_FSROOT:-}"
    ;;
  *)
    exit 1
    ;;
esac
"""


def make_fake_findmnt(tmp_path: Path) -> Path:
    fake_findmnt_path = tmp_path / "findmnt"
    fake_findmnt_path.write_text(FAKE_FINDMNT_SCRIPT)
    fake_findmnt_path.chmod(0o755)
    return fake_findmnt_path


def run_guard(tmp_path: Path, env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ["PATH"],
        "FINDMNT_BIN": str(make_fake_findmnt(tmp_path)),
        "ROOT_TARGET": "/",
        "HOME_TARGET": "/home",
        "ROOT_FSROOT": "/root",
        "HOME_FSROOT": "/home",
    }
    env.update(env_overrides)
    return subprocess.run(
        ["sh", str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_guard_accepts_root_and_home_btrfs_subvolumes_on_same_filesystem(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_guard_accepts_separate_btrfs_subvolumes_without_specific_names(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_FSROOT": "/system",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_FSROOT": "/users",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_guard_rejects_non_btrfs_root_filesystem(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "ext4",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 1


def test_guard_accepts_arch_style_at_subvolumes_on_same_filesystem(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_FSROOT": "/@",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_FSROOT": "/@home",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_guard_rejects_home_when_it_is_not_a_mountpoint(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_FSROOT": "/@",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_TARGET": "/",
            "HOME_FSROOT": "/@",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 1


def test_guard_rejects_home_when_it_is_the_same_subvolume_as_root(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_FSROOT": "/@",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_FSROOT": "/@",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 1


def test_guard_rejects_home_on_different_filesystem(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_FSROOT": "/@",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_FSROOT": "/@",
            "HOME_MAJMIN": "259:3",
        },
    )

    assert completed.returncode == 1

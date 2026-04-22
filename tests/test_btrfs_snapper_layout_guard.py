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
  /:OPTIONS)
    printf '%s\\n' "${ROOT_OPTIONS:-}"
    ;;
  /:MAJ:MIN)
    printf '%s\\n' "${ROOT_MAJMIN:-}"
    ;;
  /home:FSTYPE)
    printf '%s\\n' "${HOME_FSTYPE:-}"
    ;;
  /home:OPTIONS)
    printf '%s\\n' "${HOME_OPTIONS:-}"
    ;;
  /home:MAJ:MIN)
    printf '%s\\n' "${HOME_MAJMIN:-}"
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
    env = {"PATH": os.environ["PATH"], "FINDMNT_BIN": str(make_fake_findmnt(tmp_path))}
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
            "ROOT_OPTIONS": "rw,relatime,subvol=/root,subvolid=256",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_OPTIONS": "rw,relatime,subvol=/home,subvolid=257",
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
            "ROOT_OPTIONS": "rw,relatime",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_OPTIONS": "rw,relatime,subvol=/home,subvolid=257",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 1


def test_guard_rejects_non_matching_subvolume_layout(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_OPTIONS": "rw,relatime,subvol=/@,subvolid=256",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_OPTIONS": "rw,relatime,subvol=/@home,subvolid=257",
            "HOME_MAJMIN": "259:2",
        },
    )

    assert completed.returncode == 1


def test_guard_rejects_home_on_different_filesystem(tmp_path: Path) -> None:
    completed = run_guard(
        tmp_path,
        {
            "ROOT_FSTYPE": "btrfs",
            "ROOT_OPTIONS": "rw,relatime,subvol=/root,subvolid=256",
            "ROOT_MAJMIN": "259:2",
            "HOME_FSTYPE": "btrfs",
            "HOME_OPTIONS": "rw,relatime,subvol=/home,subvolid=257",
            "HOME_MAJMIN": "259:3",
        },
    )

    assert completed.returncode == 1

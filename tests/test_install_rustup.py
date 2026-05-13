from __future__ import annotations

from pathlib import Path
import os
import subprocess
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/install_rustup.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip())
    path.chmod(0o755)


def run_installer(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "FAKE_BIN_DIR": str(fake_bin),
            "CALL_LOG": str(tmp_path / "calls.log"),
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def install_fake_upstream_rustup(fake_bin: Path) -> None:
    write_executable(
        fake_bin / "installer-template",
        """
        #!/bin/sh
        mkdir -p "$HOME/.cargo/bin"
        cp "$FAKE_BIN_DIR/rustup-template" "$HOME/.cargo/bin/rustup"
        chmod +x "$HOME/.cargo/bin/rustup"
        """,
    )
    write_executable(
        fake_bin / "rustup-template",
        """
        #!/bin/sh
        printf 'rustup %s\n' "$*" >> "$CALL_LOG"
        if [ "$1" = "show" ] && [ "$2" = "active-toolchain" ]; then
          exit 1
        fi
        exit 0
        """,
    )
    write_executable(
        fake_bin / "curl",
        """
        #!/bin/sh
        printf 'curl %s\n' "$*" >> "$CALL_LOG"
        while [ "$#" -gt 0 ]; do
          if [ "$1" = "-o" ]; then
            output_path="$2"
            break
          fi
          shift
        done
        cp "$FAKE_BIN_DIR/installer-template" "$output_path"
        chmod +x "$output_path"
        """,
    )


def test_installs_upstream_rustup_and_bootstraps_stable_toolchain(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_upstream_rustup(fake_bin)
    write_executable(
        fake_bin / "pacman",
        """
        #!/bin/sh
        printf 'pacman should not be called\n' >> "$CALL_LOG"
        exit 99
        """,
    )
    write_executable(
        fake_bin / "sudo",
        """
        #!/bin/sh
        printf 'sudo should not be called\n' >> "$CALL_LOG"
        exit 99
        """,
    )

    run_installer(tmp_path)

    call_lines = (tmp_path / "calls.log").read_text().splitlines()
    assert call_lines[0].startswith("curl --proto =https -sSf https://sh.rustup.rs -o ")
    assert call_lines[1:] == [
        "rustup show active-toolchain",
        "rustup default stable",
    ]


def test_existing_rustup_with_active_toolchain_skips_installer(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "rustup",
        """
        #!/bin/sh
        printf 'rustup %s\n' "$*" >> "$CALL_LOG"
        if [ "$1" = "show" ] && [ "$2" = "active-toolchain" ]; then
          printf 'stable-x86_64-unknown-linux-gnu (default)\n'
        fi
        exit 0
        """,
    )
    write_executable(
        fake_bin / "pacman",
        """
        #!/bin/sh
        printf 'pacman should not be called\n' >> "$CALL_LOG"
        exit 99
        """,
    )
    write_executable(
        fake_bin / "curl",
        """
        #!/bin/sh
        printf 'curl should not be called\n' >> "$CALL_LOG"
        exit 99
        """,
    )

    run_installer(tmp_path)

    assert (tmp_path / "calls.log").read_text().splitlines() == [
        "rustup show active-toolchain",
    ]

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/install_rustup.sh"
BASH = Path("/usr/bin/bash") if Path("/usr/bin/bash").exists() else Path("/bin/bash")


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip())
    path.chmod(0o755)


def link_required_tool(tool_bin: Path, name: str) -> None:
    tool_path = shutil.which(name)
    assert tool_path is not None, f"test host is missing {name}"
    (tool_bin / name).symlink_to(tool_path)


def prepare_test_path(tmp_path: Path, fake_bin: Path) -> str:
    tool_bin = tmp_path / "tools"
    tool_bin.mkdir(exist_ok=True)
    for tool_name in ["chmod", "cp", "dirname", "mkdir", "mktemp", "pwd", "rm", "sh", "xargs"]:
        link_required_tool(tool_bin, tool_name)
    return f"{fake_bin}:{tool_bin}"


def run_installer(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": prepare_test_path(tmp_path, fake_bin),
            "FAKE_BIN_DIR": str(fake_bin),
            "CALL_LOG": str(tmp_path / "calls.log"),
        }
    )
    return subprocess.run(
        [str(BASH), str(SCRIPT)],
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


def install_fake_arch_package_manager(fake_bin: Path) -> None:
    write_executable(
        fake_bin / "pacman",
        """
        #!/bin/sh
        printf 'pacman %s\n' "$*" >> "$CALL_LOG"
        if [ "$1" = "-Q" ]; then
          exit 1
        fi
        cp "$FAKE_BIN_DIR/rustup-template" "$FAKE_BIN_DIR/rustup"
        chmod +x "$FAKE_BIN_DIR/rustup"
        exit 0
        """,
    )
    write_executable(
        fake_bin / "sudo",
        """
        #!/bin/sh
        printf 'sudo %s\n' "$*" >> "$CALL_LOG"
        exec "$@"
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


def test_installs_upstream_rustup_and_bootstraps_stable_toolchain_with_components(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_upstream_rustup(fake_bin)

    run_installer(tmp_path)

    call_lines = (tmp_path / "calls.log").read_text().splitlines()
    assert call_lines[0].startswith("curl --proto =https -sSf https://sh.rustup.rs -o ")
    assert call_lines[1:] == [
        "rustup show active-toolchain",
        "rustup default stable",
        "rustup component add clippy rustfmt rust-src",
    ]


def test_installs_arch_rustup_with_pacman_when_pacman_is_available(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_arch_package_manager(fake_bin)
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
        "pacman -Q -- rustup",
        "sudo pacman -S --needed --noconfirm rustup",
        "pacman -S --needed --noconfirm rustup",
        "rustup show active-toolchain",
        "rustup default stable",
        "rustup component add clippy rustfmt rust-src",
    ]


def test_existing_home_rustup_does_not_block_arch_package_migration(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_home_rustup = tmp_path / "home/.cargo/bin/rustup"
    fake_home_rustup.parent.mkdir(parents=True)
    write_executable(
        fake_home_rustup,
        """
        #!/bin/sh
        printf 'home rustup should not be called\n' >> "$CALL_LOG"
        exit 99
        """,
    )
    install_fake_arch_package_manager(fake_bin)

    run_installer(tmp_path)

    assert (tmp_path / "calls.log").read_text().splitlines() == [
        "pacman -Q -- rustup",
        "sudo pacman -S --needed --noconfirm rustup",
        "pacman -S --needed --noconfirm rustup",
        "rustup show active-toolchain",
        "rustup default stable",
        "rustup component add clippy rustfmt rust-src",
    ]


def test_existing_rustup_with_active_toolchain_skips_installer_but_adds_components(tmp_path: Path) -> None:
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
        "rustup component add clippy rustfmt rust-src",
    ]

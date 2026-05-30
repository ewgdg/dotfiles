from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_PARU = REPO_ROOT / "scripts/install_paru.sh"
INSTALL_ARCH_PACKAGES = REPO_ROOT / "scripts/install_arch_packages.sh"
SH = Path("/bin/sh")


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip())
    path.chmod(0o755)


def link_required_tool(tool_bin: Path, name: str) -> None:
    tool_path = shutil.which(name)
    assert tool_path is not None, f"test host is missing {name}"
    (tool_bin / name).symlink_to(tool_path)


def base_env(tmp_path: Path, fake_bin: Path) -> dict[str, str]:
    tool_bin = tmp_path / "tools"
    tool_bin.mkdir(exist_ok=True)
    for tool_name in ["cat", "chmod", "dirname", "id", "mkdir", "pwd", "sh", "xargs"]:
        link_required_tool(tool_bin, tool_name)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "PATH": f"{fake_bin}:{tool_bin}",
            "FAKE_BIN_DIR": str(fake_bin),
            "CALL_LOG": str(tmp_path / "calls.log"),
        }
    )
    (tmp_path / "home").mkdir()
    return env


def install_fake_bootstrap_tools(fake_bin: Path) -> None:
    write_executable(
        fake_bin / "sudo",
        """
        #!/bin/sh
        printf 'sudo %s\n' "$*" >> "$CALL_LOG"
        exec "$@"
        """,
    )
    write_executable(
        fake_bin / "pacman",
        """
        #!/bin/sh
        printf 'pacman %s\n' "$*" >> "$CALL_LOG"
        if [ "$1" = "-Q" ]; then
          exit 1
        fi
        exit 0
        """,
    )
    write_executable(
        fake_bin / "git",
        """
        #!/bin/sh
        printf 'git %s\n' "$*" >> "$CALL_LOG"
        if [ "$1" = "clone" ]; then
          mkdir -p "$3/.git"
          exit 0
        fi
        if [ "$1" = "-C" ]; then
          exit 0
        fi
        exit 99
        """,
    )
    write_executable(
        fake_bin / "makepkg",
        """#!/bin/sh
printf 'makepkg %s cwd=%s\n' "$*" "$(pwd)" >> "$CALL_LOG"
cat > "$FAKE_BIN_DIR/paru" <<'PARU'
#!/bin/sh
printf 'paru %s\n' "$*" >> "$CALL_LOG"
exit 0
PARU
chmod +x "$FAKE_BIN_DIR/paru"
""",
    )


def test_existing_paru_skips_bootstrap(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(fake_bin / "paru", "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "pacman",
        """
        #!/bin/sh
        printf 'pacman should not be called\n' >> "$CALL_LOG"
        exit 99
        """,
    )

    subprocess.run(
        [str(SH), str(INSTALL_PARU)],
        cwd=REPO_ROOT,
        env=base_env(tmp_path, fake_bin),
        capture_output=True,
        text=True,
        check=True,
    )

    assert not (tmp_path / "calls.log").exists()


def test_bootstraps_paru_from_aur_package(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_bootstrap_tools(fake_bin)
    env = base_env(tmp_path, fake_bin)

    subprocess.run(
        [str(SH), str(INSTALL_PARU)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    source_dir = tmp_path / "cache/makepkg/aur-bootstrap/paru-bin"
    assert (tmp_path / "calls.log").read_text().splitlines() == [
        "sudo pacman -S --needed --noconfirm base-devel git",
        "pacman -S --needed --noconfirm base-devel git",
        f"git clone https://aur.archlinux.org/paru-bin.git {source_dir}",
        f"makepkg -si --needed --noconfirm cwd={source_dir}",
    ]


def test_arch_package_installer_bootstraps_paru_before_installing_missing_packages(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_bootstrap_tools(fake_bin)
    env = base_env(tmp_path, fake_bin)

    subprocess.run(
        [str(SH), str(INSTALL_ARCH_PACKAGES), "ripgrep"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    source_dir = tmp_path / "cache/makepkg/aur-bootstrap/paru-bin"
    assert (tmp_path / "calls.log").read_text().splitlines() == [
        "pacman -Q -- ripgrep",
        "sudo pacman -S --needed --noconfirm base-devel git",
        "pacman -S --needed --noconfirm base-devel git",
        f"git clone https://aur.archlinux.org/paru-bin.git {source_dir}",
        f"makepkg -si --needed --noconfirm cwd={source_dir}",
        "paru -S --needed --noconfirm --skipreview --useask ripgrep",
    ]

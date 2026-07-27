from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
UPGRADE_COMMAND = REPO_ROOT / "packages/topgrade/files/local/bin/upgrade"
TOPGRADE_CONFIG = REPO_ROOT / "packages/topgrade/files/config/topgrade.toml"


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


def command_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    projects_dir = tmp_path / "Projects"

    write_executable(
        fake_bin / "topgrade",
        """#!/bin/sh
printf 'topgrade'
for argument in "$@"; do
    printf '|%s' "$argument"
done
printf '\n'
exit "${TOPGRADE_EXIT_STATUS:-0}"
""",
    )
    write_executable(
        fake_bin / "xdg-user-dir",
        """#!/bin/sh
[ "$#" -eq 1 ] && [ "$1" = PROJECTS ] || exit 2
printf '%s\n' "$FAKE_PROJECTS_DIR"
""",
    )

    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["FAKE_PROJECTS_DIR"] = str(projects_dir)
    return environment, projects_dir


def run_upgrade(
    tmp_path: Path,
    *arguments: str,
    environment_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment, _ = command_environment(tmp_path)
    environment.update(environment_overrides or {})
    return subprocess.run(
        ["sh", str(UPGRADE_COMMAND), *arguments],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_no_arguments_delegate_to_topgrade(tmp_path: Path) -> None:
    completed = run_upgrade(tmp_path)

    assert completed.returncode == 0
    assert completed.stdout == "topgrade\n"


def test_topgrade_arguments_are_forwarded_exactly(tmp_path: Path) -> None:
    completed = run_upgrade(tmp_path, "--only", "cargo", "value with spaces")

    assert completed.returncode == 0
    assert completed.stdout == "topgrade|--only|cargo|value with spaces\n"


def test_topgrade_exit_status_is_preserved(tmp_path: Path) -> None:
    completed = run_upgrade(
        tmp_path,
        "--only",
        "flatpak",
        environment_overrides={"TOPGRADE_EXIT_STATUS": "23"},
    )

    assert completed.returncode == 23


def test_exact_services_subcommand_delegates_to_services_updater(tmp_path: Path) -> None:
    environment, projects_dir = command_environment(tmp_path)
    write_executable(
        projects_dir / "services/services.sh",
        """#!/bin/sh
printf 'services|%s\n' "$*"
exit "${SERVICES_EXIT_STATUS:-0}"
""",
    )

    completed = subprocess.run(
        ["sh", str(UPGRADE_COMMAND), "services"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "services|update\n"


def test_services_updater_exit_status_is_preserved(tmp_path: Path) -> None:
    environment, projects_dir = command_environment(tmp_path)
    environment["SERVICES_EXIT_STATUS"] = "29"
    write_executable(
        projects_dir / "services/services.sh",
        "#!/bin/sh\nexit \"${SERVICES_EXIT_STATUS:-0}\"\n",
    )

    completed = subprocess.run(
        ["sh", str(UPGRADE_COMMAND), "services"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert completed.returncode == 29


def test_services_with_extra_arguments_are_forwarded_to_topgrade(tmp_path: Path) -> None:
    completed = run_upgrade(tmp_path, "services", "extra")

    assert completed.returncode == 0
    assert completed.stdout == "topgrade|services|extra\n"


def test_missing_services_updater_fails_with_actionable_path(tmp_path: Path) -> None:
    environment, projects_dir = command_environment(tmp_path)

    completed = subprocess.run(
        ["sh", str(UPGRADE_COMMAND), "services"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    expected_path = projects_dir / "services/services.sh"
    assert completed.returncode != 0
    assert str(expected_path) in completed.stderr
    assert "not executable" in completed.stderr


def test_failed_projects_directory_lookup_has_actionable_error(tmp_path: Path) -> None:
    environment, _ = command_environment(tmp_path)
    fake_xdg_user_dir = Path(environment["PATH"].split(os.pathsep, 1)[0]) / "xdg-user-dir"
    write_executable(fake_xdg_user_dir, "#!/bin/sh\nexit 17\n")

    completed = subprocess.run(
        ["sh", str(UPGRADE_COMMAND), "services"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert completed.returncode != 0
    assert "Could not resolve projects directory" in completed.stderr


def test_topgrade_policy_keeps_destructive_or_duplicated_steps_explicit() -> None:
    with TOPGRADE_CONFIG.open("rb") as config_file:
        config = tomllib.load(config_file)

    assert config["misc"] == {
        "no_self_update": True,
        "ask_retry": True,
        "auto_retry": 0,
        "disable": ["containers"],
    }
    assert config["linux"]["arch_package_manager"] == "paru"
    assert config["git"] == {
        "pull_predefined": False,
        "repos": ["~/Projects/dotfiles"],
    }
    assert config["cargo"]["git"] is True


def test_topgrade_package_owns_install_config_and_launcher_targets() -> None:
    with (REPO_ROOT / "packages/topgrade/package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    targets = package["targets"]
    assert targets["topgrade_installed"]["probe"] == (
        "{{ PROBE_PACKAGES_INSTALLED }} topgrade"
    )
    assert targets["topgrade_installed"]["hooks"]["pre_push"] == (
        "{{ INSTALL }} topgrade"
    )
    assert targets["f_config_topgrade_toml"]["path"] == "~/.config/topgrade.toml"
    assert targets["f_local_bin_upgrade"]["path"] == "~/.local/bin/upgrade"


def test_go_toolchain_package_bootstraps_gup_only_when_missing() -> None:
    with (REPO_ROOT / "packages/go-lang/package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    gup_target = package["targets"]["gup_installed"]
    assert "command -v gup" in gup_target["probe"]
    assert gup_target["hooks"]["pre_push"] == (
        "go install github.com/nao1215/gup@latest"
    )

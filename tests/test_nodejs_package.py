from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_PACKAGE_PATH = REPO_ROOT / "packages/nodejs/package.toml"
CORE_ENV_PATH = REPO_ROOT / "packages/shell/files/env.core.sh"


def test_nodejs_package_installs_pnpm_with_each_os_node_toolchain() -> None:
    package = tomllib.loads(NODE_PACKAGE_PATH.read_text(encoding="utf-8"))
    arch_profile = tomllib.loads(
        (REPO_ROOT / "profiles/os/arch.toml").read_text(encoding="utf-8")
    )
    mac_profile = tomllib.loads(
        (REPO_ROOT / "profiles/os/mac.toml").read_text(encoding="utf-8")
    )

    toolchain_target = package["targets"]["nodejs_toolchain_installed"]
    assert toolchain_target["sync_policy"] == "push-only"
    assert (
        toolchain_target["probe"]
        == "{{ PROBE_PACKAGES_INSTALLED }} {{ NODEJS_INSTALL_PACKAGES }} bun fnm"
    )
    assert toolchain_target["hooks"]["pre_push"] == [
        "{{ INSTALL }} {{ NODEJS_INSTALL_PACKAGES }}",
        "{{ INSTALL }} bun fnm",
    ]
    assert "hooks" not in package
    assert "pnpm" in arch_profile["vars"]["NODEJS_INSTALL_PACKAGES"].split()
    assert "pnpm" in mac_profile["vars"]["NODEJS_INSTALL_PACKAGES"].split()


def test_core_env_exports_pnpm_home_and_adds_its_bin_directory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    data_home = tmp_path / "data"
    pnpm_bin = data_home / "pnpm/bin"
    pnpm_bin.mkdir(parents=True)

    env = os.environ.copy()
    env.pop("PNPM_HOME", None)
    env.update(
        {"HOME": str(home), "XDG_DATA_HOME": str(data_home), "PATH": "/usr/bin:/bin"}
    )

    completed = subprocess.run(
        [
            "sh",
            "-c",
            f'. "{CORE_ENV_PATH}"; printf "%s\\n%s\\n" "$PNPM_HOME" "$PATH"',
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    pnpm_home, path = completed.stdout.strip().splitlines()
    assert pnpm_home == str(data_home / "pnpm")
    assert path.split(":")[0] == str(pnpm_bin)
    assert path.split(":").count(str(pnpm_bin)) == 1

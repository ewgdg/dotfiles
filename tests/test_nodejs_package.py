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


def test_nodejs_package_tracks_the_lts_as_the_fnm_default() -> None:
    package = tomllib.loads(NODE_PACKAGE_PATH.read_text(encoding="utf-8"))

    target = package["targets"]["fnm_default_node_on_lts"]
    assert target["sync_policy"] == "push-only"
    assert (
        target["probe"]
        == 'sh "$DOTMAN_PACKAGE_ROOT/scripts/fnm_default_lts.sh" probe'
    )
    assert target["hooks"]["pre_push"] == (
        'sh "$DOTMAN_PACKAGE_ROOT/scripts/fnm_default_lts.sh" apply'
    )

    script = (REPO_ROOT / "packages/nodejs/scripts/fnm_default_lts.sh").read_text(
        encoding="utf-8"
    )
    # Crossing a node major invalidates every installed native binding, so the
    # apply path must rebuild the global packages through the new default node.
    assert "fnm exec --using=default -- npm rebuild -g" in script
    assert 'fnm default "${latest}"' in script
    # An unavailable network keeps the installed default instead of forcing churn.
    assert "could not resolve the latest LTS; keeping" in script
    # Each node tree is ~200 MB, so the replaced one is removed. That is safe only
    # because fnm env links each shell through the default alias; relinking a shell
    # link directly at a version tree would sever that hop and stop the shell from
    # following later fnm default moves.
    assert 'fnm uninstall "${current}"' in script
    assert "ln -sfn" not in script
    assert "fnm_multishells" not in script


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

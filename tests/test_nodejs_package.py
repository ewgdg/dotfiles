from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_PACKAGE_PATH = REPO_ROOT / "packages/nodejs/package.toml"
NODEJS_SCRIPTS = REPO_ROOT / "packages/nodejs/scripts"
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


def run_nodejs_script(
    script_name: str,
    action: str,
    tmp_path: Path,
    stubs: dict[str, str],
    *,
    label: str = "run",
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run a package script with stub commands first on PATH.

    The stub bin directory and call log are per-label, while HOME and
    XDG_STATE_HOME are shared across calls in one test so recorded state persists.
    """
    run_dir = tmp_path / label
    bin_dir = run_dir / "bin"
    bin_dir.mkdir(parents=True)
    calls = run_dir / "calls.log"

    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(tmp_path / "home"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "CALLS": str(calls),
        }
    )
    env.pop("FNM_DIR", None)
    if extra_env:
        env.update(extra_env)

    completed = subprocess.run(
        ["sh", str(NODEJS_SCRIPTS / script_name), action],
        env=env,
        capture_output=True,
        text=True,
    )
    return completed, calls


def test_nodejs_package_wires_the_node_ownership_targets() -> None:
    package = tomllib.loads(NODE_PACKAGE_PATH.read_text(encoding="utf-8"))

    assert package["targets"]["fnm_default_alias_removed"] == {
        "sync_policy": "push-only",
        "probe": 'sh "$DOTMAN_PACKAGE_ROOT/scripts/fnm_default_alias_removed.sh" probe',
        "hooks": {
            "pre_push": 'sh "$DOTMAN_PACKAGE_ROOT/scripts/fnm_default_alias_removed.sh" apply'
        },
    }
    assert package["targets"]["npm_globals_match_node_abi"] == {
        "sync_policy": "push-only",
        "probe": 'sh "$DOTMAN_PACKAGE_ROOT/scripts/npm_globals_abi.sh" probe',
        "hooks": {"pre_push": 'sh "$DOTMAN_PACKAGE_ROOT/scripts/npm_globals_abi.sh" apply'},
    }
    # Declaration order is the execution order, and the rebuild has to run under
    # the node the install target just put in place.
    assert list(package["targets"]) == [
        "f_npmrc",
        "nodejs_toolchain_installed",
        "fnm_default_alias_removed",
        "npm_globals_match_node_abi",
    ]


def test_nodejs_package_names_the_lts_line_in_the_profile() -> None:
    arch_profile = tomllib.loads(
        (REPO_ROOT / "profiles/os/arch.toml").read_text(encoding="utf-8")
    )
    packages = arch_profile["vars"]["NODEJS_INSTALL_PACKAGES"].split()

    # Arch's own nodejs tracks the current line, which reaches devspace's upper
    # bound on pacman's schedule; the LTS package is the one that can be held.
    assert "nodejs-lts-krypton" in packages
    assert "nodejs" not in packages
    # The LTS line is named in the repo rather than resolved from the network at
    # push time, so moving lines is a reviewable change.
    assert not (NODEJS_SCRIPTS / "fnm_default_lts.sh").exists()


def test_fnm_default_alias_is_removed_only_while_it_exists(tmp_path: Path) -> None:
    fnm_stub = (
        "#!/bin/sh\n"
        'echo "$@" >> "$CALLS"\n'
        'if [ "$1" = default ]; then echo v22.23.1; fi\n'
    )

    probe, probe_calls = run_nodejs_script(
        "fnm_default_alias_removed.sh", "probe", tmp_path, {"fnm": fnm_stub}, label="probe"
    )
    assert probe.returncode == 0
    assert "uninstall" not in probe_calls.read_text(encoding="utf-8")

    applied, apply_calls = run_nodejs_script(
        "fnm_default_alias_removed.sh", "apply", tmp_path, {"fnm": fnm_stub}, label="apply"
    )
    assert applied.returncode == 0
    # fnm uninstall also drops the aliases pointing at the version, so removing the
    # tree is what clears the alias that shadows the system node.
    assert "uninstall v22.23.1" in apply_calls.read_text(encoding="utf-8")

    no_alias = '#!/bin/sh\necho "$@" >> "$CALLS"\nexit 1\n'
    current, _ = run_nodejs_script(
        "fnm_default_alias_removed.sh", "probe", tmp_path, {"fnm": no_alias}, label="none"
    )
    assert current.returncode == 100


def test_global_npm_packages_rebuild_when_the_node_abi_moves(tmp_path: Path) -> None:
    abi_file = tmp_path / "abi"
    abi_file.write_text("137\n", encoding="utf-8")
    node_stub = (
        "#!/bin/sh\n"
        'echo "$@" >> "$CALLS"\n'
        'if [ "$1" = -p ]; then cat "$ABI_FILE"; fi\n'
    )
    npm_stub = '#!/bin/sh\necho "$@" >> "$CALLS"\n'
    stubs = {"node": node_stub, "npm": npm_stub}
    extra_env = {"ABI_FILE": str(abi_file)}
    stamp = tmp_path / "state/dotfiles/nodejs/npm-globals-abi"

    # Nothing recorded yet, so the shared prefix cannot be trusted.
    probe, probe_calls = run_nodejs_script(
        "npm_globals_abi.sh", "probe", tmp_path, stubs, label="p1", extra_env=extra_env
    )
    assert probe.returncode == 0
    assert "rebuild" not in probe_calls.read_text(encoding="utf-8")

    applied, apply_calls = run_nodejs_script(
        "npm_globals_abi.sh", "apply", tmp_path, stubs, label="a1", extra_env=extra_env
    )
    assert applied.returncode == 0
    assert "rebuild -g" in apply_calls.read_text(encoding="utf-8")
    assert stamp.read_text(encoding="utf-8").strip() == "137"

    current, _ = run_nodejs_script(
        "npm_globals_abi.sh", "probe", tmp_path, stubs, label="p2", extra_env=extra_env
    )
    assert current.returncode == 100

    # A new LTS line moves the ABI, which invalidates every binding in the prefix.
    abi_file.write_text("147\n", encoding="utf-8")
    moved, _ = run_nodejs_script(
        "npm_globals_abi.sh", "probe", tmp_path, stubs, label="p3", extra_env=extra_env
    )
    assert moved.returncode == 0

    # A failing rebuild must not be recorded as current, or the next push would
    # skip it.
    failing_npm = '#!/bin/sh\necho "$@" >> "$CALLS"\nexit 1\n'
    failed, _ = run_nodejs_script(
        "npm_globals_abi.sh",
        "apply",
        tmp_path,
        {"node": node_stub, "npm": failing_npm},
        label="a2",
        extra_env=extra_env,
    )
    assert failed.returncode != 0
    assert stamp.read_text(encoding="utf-8").strip() == "137"


def test_global_npm_rebuild_is_skipped_without_a_node(tmp_path: Path) -> None:
    npm_stub = '#!/bin/sh\necho "$@" >> "$CALLS"\n'
    node_stub = '#!/bin/sh\necho "$@" >> "$CALLS"\nexit 1\n'

    completed, calls = run_nodejs_script(
        "npm_globals_abi.sh",
        "probe",
        tmp_path,
        {"node": node_stub, "npm": npm_stub},
        label="probe",
    )

    # Installing node is the install target's job; a rebuild here would only fail.
    assert completed.returncode == 100
    assert not calls.exists() or "rebuild" not in calls.read_text(encoding="utf-8")


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

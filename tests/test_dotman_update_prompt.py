from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import pty
import pytest
import select
import shutil
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DOTMAN_PATH = REPO_ROOT / "dotfiles" / "bin" / "dotman"
DOTMAN_PY_PATH = REPO_ROOT / "scripts" / "dotman.py"

DOTMAN_SPEC = importlib.util.spec_from_file_location("dotman_py", DOTMAN_PY_PATH)
assert DOTMAN_SPEC is not None
assert DOTMAN_SPEC.loader is not None
DOTMAN_MODULE = importlib.util.module_from_spec(DOTMAN_SPEC)
sys.modules[DOTMAN_SPEC.name] = DOTMAN_MODULE
DOTMAN_SPEC.loader.exec_module(DOTMAN_MODULE)
DotManager = DOTMAN_MODULE.DotManager


def create_repro_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "dotdrop-repro"
    repo_source_dir = repo_root / "dotfiles" / "config" / "app"
    live_dir = tmp_path / "home" / ".config" / "app"
    workdir = tmp_path / "workdir"

    repo_source_dir.mkdir(parents=True)
    live_dir.mkdir(parents=True)
    workdir.mkdir()

    config_path = repo_root / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "config:",
                "  backup: false",
                "  create: true",
                "  dotpath: dotfiles",
                f"  workdir: {workdir}",
                "",
                "dotfiles:",
                "  d_app:",
                "    src: config/app",
                f"    dst: {live_dir}",
                "    upignore:",
                "      - '*/__pycache__'",

                "profiles:",
                "  repro:",
                "    dotfiles:",
                "      - d_app",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (repo_source_dir / "settings.toml").write_text('value = "repo"\n', encoding="utf-8")
    (live_dir / "settings.toml").write_text('value = "live"\n', encoding="utf-8")
    (live_dir / "extra.toml").write_text('value = "extra"\n', encoding="utf-8")

    repo_cache_dir = repo_source_dir / "__pycache__"
    live_cache_dir = live_dir / "__pycache__"
    repo_cache_dir.mkdir()
    live_cache_dir.mkdir()
    (repo_cache_dir / "ignored.pyc").write_text("repo-cache\n", encoding="utf-8")
    (live_cache_dir / "ignored.pyc").write_text("live-cache\n", encoding="utf-8")

    return config_path, repo_source_dir, live_dir


def create_template_repro_project(tmp_path: Path, *, with_include_directive: bool = False) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "dotdrop-template-repro"
    repo_source_path = repo_root / "dotfiles" / "profile"
    live_path = tmp_path / "home" / ".profile"
    workdir = tmp_path / "workdir"
    helper_dir = repo_root / "scripts"
    core_env_path = repo_root / "dotfiles" / "env.core.sh"

    repo_source_path.parent.mkdir(parents=True)
    live_path.parent.mkdir(parents=True)
    workdir.mkdir()
    helper_dir.mkdir()
    (helper_dir / "dotdrop_template_update.py").symlink_to(
        REPO_ROOT / "scripts" / "dotdrop_template_update.py"
    )
    core_env_path.write_text(": # core env\n", encoding="utf-8")

    config_path = repo_root / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "config:",
                "  backup: false",
                "  create: true",
                "  dotpath: dotfiles",
                f"  workdir: {workdir}",
                "",
                "dotfiles:",
                "  f_profile:",
                "    src: profile",
                f"    dst: {live_path}",
                "",
                "profiles:",
                "  repro:",
                "    dotfiles:",
                "      - f_profile",
                "",
            ]
        ),
        encoding="utf-8",
    )

    source_text = """start
{%@@ if os == \"linux\" @@%}
repo
{%@@ endif @@%}
end
"""
    live_text = "start\nlive\nend\n"

    if with_include_directive:
        source_text = """start
{%@@ include 'env.core.sh' @@%}
end
"""
        live_text = "start\nbootstrap-live\nend\n"

    repo_source_path.write_text(source_text, encoding="utf-8")
    live_path.write_text(live_text, encoding="utf-8")

    return config_path, repo_source_path, live_path


def build_isolated_dotman_env(base_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(base_dir)
    env["XDG_STATE_HOME"] = str(base_dir / "state")
    env.pop("DOTDROP_PROFILE", None)
    return env


def write_fake_uv_runner(helper_dir: Path) -> None:
    fake_uv = helper_dir / "uv"
    fake_uv.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'if [[ "$1" != "run" ]]; then',
                '  echo "fake uv only supports `uv run` in this test helper" >&2',
                "  exit 2",
                "fi",
                "shift",
                'if [[ "$1" == "--project" ]]; then',
                "  shift 2",
                "fi",
                'exec python3 "$@"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

def run_interactive_dotman(
    config_path: Path,
    target_path: Path | None,
    answer: str,
    *,
    explicit_profile: bool = True,
) -> tuple[int, str]:
    env = build_isolated_dotman_env(config_path.parent.parent)
    env["DOTDROP_CONFIG"] = str(config_path)

    command_parts = [
        str(DOTMAN_PATH),
        "update",
    ]
    if explicit_profile:
        command_parts.extend(["-p", "repro"])
    if target_path is not None:
        command_parts.append(str(target_path))

    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        command_parts,
        cwd=REPO_ROOT,
        env=env,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        text=False,
    )
    os.close(slave_fd)

    os.write(master_fd, f"{answer}\n".encode("utf-8"))
    output_chunks: list[bytes] = []
    while True:
        if process.poll() is not None:
            ready, _, _ = select.select([master_fd], [], [], 0)
            if not ready:
                break

        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if not ready:
            continue

        try:
            chunk = os.read(master_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        output_chunks.append(chunk)

    os.close(master_fd)
    return_code = process.wait()
    output = b"".join(output_chunks).decode("utf-8", errors="replace")
    return return_code, output


def run_dotman(
    config_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DOTDROP_CONFIG"] = str(config_path)
    if extra_env is not None:
        env.update(extra_env)

    return subprocess.run(
        [str(DOTMAN_PATH), *args],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def create_fake_dotdrop_tools(
    tmp_path: Path,
    *,
    repo_source_dir: Path,
    live_dir: Path,
    compare_output: str,
    install_dry_output: str,
) -> tuple[dict[str, str], Path, Path, Path]:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    dotdrop_args_file = tmp_path / "dotdrop-args.txt"
    sudo_args_file = tmp_path / "sudo-args.txt"
    phase_runs_file = tmp_path / "phase-runs.txt"

    fake_dotdrop = helper_dir / "dotdrop"
    fake_dotdrop.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" >> "$DOTDROP_ARGS_FILE"
printf -- '--\n' >> "$DOTDROP_ARGS_FILE"

if [[ "$1" == "compare" ]]; then
  printf '%s\n' "$DOTDROP_COMPARE_OUTPUT"
  exit 0
fi

if [[ "$1" == "files" ]]; then
  printf '%s\n' "$DOTDROP_FILES_OUTPUT"
  exit 0
fi

if [[ "$1" == "install" ]]; then
  shift
  for arg in "$@"; do
    if [[ "$arg" == "-d" ]]; then
      printf '%s\n' "$DOTDROP_INSTALL_DRY_OUTPUT"
      exit 0
    fi
  done

  printf 'install\n' >> "$DOTDROP_PHASE_RUNS_FILE"
  exit 0
fi

exit 0
""",
        encoding="utf-8",
    )
    fake_dotdrop.chmod(0o755)

    fake_sudo = helper_dir / "sudo"
    fake_sudo.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" >> "$SUDO_ARGS_FILE"
printf -- '--\n' >> "$SUDO_ARGS_FILE"
"$@"
""",
        encoding="utf-8",
    )
    fake_sudo.chmod(0o755)

    write_fake_uv_runner(helper_dir)

    env = os.environ.copy()
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_ARGS_FILE"] = str(dotdrop_args_file)
    env["DOTDROP_COMPARE_OUTPUT"] = compare_output
    env["DOTDROP_INSTALL_DRY_OUTPUT"] = install_dry_output
    env["DOTDROP_FILES_OUTPUT"] = (
        f'd_app,dst:{live_dir},src:{repo_source_dir},link:nolink,chmod:None'
    )
    env["DOTDROP_PHASE_RUNS_FILE"] = str(phase_runs_file)
    env["SUDO_ARGS_FILE"] = str(sudo_args_file)
    return env, dotdrop_args_file, sudo_args_file, phase_runs_file


def test_directory_update_can_be_skipped_interactively(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotman(config_path, live_dir, "n\nn")

    assert exit_code == 0
    assert output.count('overwrite dotfiles path "') == 1
    assert output.count('import live path into dotfiles "') == 1
    assert 'overwrite dotfiles path "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'
    assert not (repo_source_dir / "extra.toml").exists()


def test_declined_update_backup_restores_repo_file_after_simulated_update(tmp_path: Path) -> None:
    source_path = tmp_path / "repo" / "tracked.toml"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("repo\n", encoding="utf-8")

    manager = DotManager(["update"])

    manager.backup_declined_update_path(source_path)
    assert source_path.read_text(encoding="utf-8") == "repo\n"

    source_path.write_text("updated\n", encoding="utf-8")

    manager.restore_declined_update_state()
    assert source_path.read_text(encoding="utf-8") == "repo\n"
    assert manager.declined_update_backup_dir is None


def test_parse_update_changes_maps_transform_preview_back_to_live_path(tmp_path: Path) -> None:
    manager = DotManager(["update"])
    live_path = tmp_path / "home" / "Library" / "Preferences" / "settings.plist"
    repo_path = tmp_path / "repo" / "dotfiles" / "Library" / "Preferences" / "settings.plist"
    staged_path = tmp_path / "tmp" / "dotdrop-preview" / "settings.plist"
    preview_output = "\n".join(
        [
            (
                f'\t-> executing "python3 \'/repo/scripts/plist_transform.py\' '
                f'{live_path} {staged_path} --mode strip --output-format xml"'
            ),
            f"[DRY] would cp {staged_path} {repo_path}",
            "",
        ]
    )

    changes = manager.parse_update_changes(preview_output)

    assert len(changes) == 1
    assert changes[0].source_path == repo_path
    assert changes[0].live_path == live_path
    assert changes[0].preview_transform is not None
    assert changes[0].preview_transform.output_path == staged_path


def test_declined_directory_import_removes_created_repo_file_on_restore(tmp_path: Path) -> None:
    manager = DotManager(["update"])
    source_path = tmp_path / "repo" / "live-only.toml"
    manager.backup_declined_update_path(source_path)

    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("imported\n", encoding="utf-8")

    manager.restore_declined_update_state()
    assert not source_path.exists()
    assert manager.declined_update_backup_dir is None


def test_declining_single_file_update_removes_key_from_regular_update_targets(monkeypatch, tmp_path: Path) -> None:
    manager = DotManager(["update"])
    manager.operation = "update"
    manager.parsed = DOTMAN_MODULE.ParsedArgs()
    source_path = tmp_path / "repo" / "settings.toml"
    live_path = tmp_path / "home" / ".config" / "settings.toml"
    source_path.parent.mkdir(parents=True)
    live_path.parent.mkdir(parents=True)
    source_path.write_text("repo\n", encoding="utf-8")
    live_path.write_text("live\n", encoding="utf-8")

    manager.all_keys = ["f_settings"]
    manager.source_by_key = {"f_settings": str(source_path)}
    manager.destination_by_key = {"f_settings": str(live_path)}
    manager.normalized_destination_by_key = {"f_settings": str(live_path)}
    manager.regular_update_keys = ["f_settings"]
    manager.regular_update_key_set = {"f_settings"}

    monkeypatch.setattr(
        manager,
        "collect_update_changes",
        lambda: [DOTMAN_MODULE.UpdateChange(source_path=source_path, live_path=live_path)],
    )
    monkeypatch.setattr(manager, "prompt", lambda _message: "n")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    manager.confirm_update_overwrite_targets()

    assert manager.regular_update_keys == []
    assert manager.regular_update_key_set == set()
    assert manager.declined_update_backup_entries == []


def test_directory_update_can_be_confirmed_interactively(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotman(config_path, live_dir, "y\ny")

    assert exit_code == 0
    assert 'overwrite dotfiles path "' in output
    assert 'import live path into dotfiles "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'


def test_directory_update_prompts_before_importing_live_only_file(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    live_only = live_dir / "live-only.toml"

    live_only.write_text('value = "live only"\n', encoding="utf-8")

    exit_code, output = run_interactive_dotman(config_path, live_dir, "y\nn\ny")

    assert exit_code == 0
    assert 'overwrite dotfiles path "' in output
    assert 'import live path into dotfiles "' in output
    assert 'live-only.toml' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'
    assert not (repo_source_dir / "live-only.toml").exists()


def test_default_profile_whole_update_prompt_defaults_to_yes(tmp_path: Path) -> None:
    config_path, repo_source_dir, _live_dir = create_repro_project(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("  repro:\n", "  host_linux:\n"),
        encoding="utf-8",
    )
    state_dir = tmp_path / "state" / "dotman"
    state_dir.mkdir(parents=True)
    (state_dir / "default-profile").write_text("host_linux\n", encoding="utf-8")

    exit_code, output = run_interactive_dotman(
        config_path,
        None,
        "\nn\nn",
        explicit_profile=False,
    )

    assert exit_code == 0
    assert 'Using dotdrop profile "repro"' not in output
    assert 'Update all dotfiles for profile "host_linux" [Y/n] ?' in output
    assert 'import live path into dotfiles "' in output
    assert 'overwrite dotfiles path "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'
    assert not (repo_source_dir / "extra.toml").exists()

def test_child_path_update_stays_scoped_to_requested_file(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    live_file = live_dir / "settings.toml"
    repo_other = repo_source_dir / "other.toml"
    live_other = live_dir / "other.toml"
    live_only = live_dir / "live-only.toml"

    repo_other.write_text('value = "repo other"\n', encoding="utf-8")
    live_other.write_text('value = "live other"\n', encoding="utf-8")
    live_only.write_text('value = "live only"\n', encoding="utf-8")

    exit_code, output = run_interactive_dotman(config_path, live_file, "y")

    assert exit_code == 0
    assert output.count('overwrite dotfiles path "') == 1
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert repo_other.read_text(encoding="utf-8") == 'value = "repo other"\n'
    assert not (repo_source_dir / "live-only.toml").exists()


def test_unmatched_update_path_is_rejected(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    unmatched_path = live_dir.parent / "missing" / "settings.toml"

    exit_code, output = run_interactive_dotman(config_path, unmatched_path, "y")

    assert exit_code == 2
    assert "no tracked dotdrop key matches update target" in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'


def test_unknown_command_passthrough_is_augmented_with_metadata(tmp_path: Path) -> None:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    args_file = tmp_path / "dotdrop-args.txt"
    fake_dotdrop = helper_dir / "dotdrop"
    fake_dotdrop.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" > "$DOTDROP_ARGS_FILE"
exit "${DOTDROP_EXIT_CODE:-0}"
""",
        encoding="utf-8",
    )
    fake_dotdrop.chmod(0o755)
    write_fake_uv_runner(helper_dir)

    env = build_isolated_dotman_env(tmp_path)
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_CONFIG"] = str(REPO_ROOT / "config.yaml")
    env["DOTDROP_ARGS_FILE"] = str(args_file)
    env["DOTDROP_EXIT_CODE"] = "23"

    result = subprocess.run(
        [str(DOTMAN_PATH), "compare", "--profile", "repro", "d_app"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 23
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "compare",
        "--profile=repro",
        "d_app",
        f"--cfg={REPO_ROOT / 'config.yaml'}",
    ]


def test_unknown_command_without_profile_uses_stored_default_before_passthrough(tmp_path: Path) -> None:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    args_file = tmp_path / "dotdrop-args.txt"
    fzf_marker = tmp_path / "fzf-called.txt"
    fake_dotdrop = helper_dir / "dotdrop"
    fake_dotdrop.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" > "$DOTDROP_ARGS_FILE"
""",
        encoding="utf-8",
    )
    fake_dotdrop.chmod(0o755)
    write_fake_uv_runner(helper_dir)
    fake_fzf = helper_dir / "fzf"
    fake_fzf.write_text(
        """#!/usr/bin/env bash
printf 'called\n' > "$DOTMAN_FZF_MARKER"
exit 99
""",
        encoding="utf-8",
    )
    fake_fzf.chmod(0o755)

    DOTMAN_MODULE.write_default_profile(tmp_path / "state" / "dotman", "stored-profile")

    env = build_isolated_dotman_env(tmp_path)
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_CONFIG"] = str(REPO_ROOT / "config.yaml")
    env["DOTDROP_ARGS_FILE"] = str(args_file)
    env["DOTMAN_FZF_MARKER"] = str(fzf_marker)

    result = subprocess.run(
        [str(DOTMAN_PATH), "compare", "d_app"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "compare",
        "d_app",
        f"--cfg={REPO_ROOT / 'config.yaml'}",
        "--profile=stored-profile",
    ]
    assert not fzf_marker.exists()

def test_leading_option_with_explicit_cfg_avoids_duplicate_cfg(tmp_path: Path) -> None:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    args_file = tmp_path / "dotdrop-args.txt"
    config_path = tmp_path / "custom-config.yaml"
    config_path.write_text("config:\n  dotpath: dotfiles\n", encoding="utf-8")
    fake_dotdrop = helper_dir / "dotdrop"
    fake_dotdrop.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" > "$DOTDROP_ARGS_FILE"
""",
        encoding="utf-8",
    )
    fake_dotdrop.chmod(0o755)
    write_fake_uv_runner(helper_dir)

    env = build_isolated_dotman_env(tmp_path)
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_ARGS_FILE"] = str(args_file)
    env["DOTDROP_PROFILE"] = "env-profile"

    result = subprocess.run(
        [str(DOTMAN_PATH), "--cfg", str(config_path), "compare", "d_app"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        f"--cfg={config_path}",
        "compare",
        "d_app",
        "--profile=env-profile",
    ]


def test_wrapper_sources_repo_core_env_before_running_uv(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    helper_dir = tmp_path / "bin"
    dotman_path = repo_root / "dotfiles" / "bin" / "dotman"
    core_env_path = repo_root / "dotfiles" / "env.core.sh"
    config_path = repo_root / "config.yaml"
    script_path = repo_root / "scripts" / "dotman.py"
    marker_file = tmp_path / "marker.txt"
    args_file = tmp_path / "uv-args.txt"

    helper_dir.mkdir()
    dotman_path.parent.mkdir(parents=True)
    script_path.parent.mkdir(parents=True)
    core_env_path.parent.mkdir(parents=True, exist_ok=True)

    dotman_path.write_text(DOTMAN_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    dotman_path.chmod(0o755)
    config_path.write_text("config:\n  dotpath: dotfiles\n", encoding="utf-8")
    script_path.write_text("print('placeholder')\n", encoding="utf-8")
    core_env_path.write_text(
        "\n".join(
            [
                f'export DOTMAN_WRAPPER_MARKER="{marker_file}"',
                'export DOTMAN_WRAPPER_VALUE="repo-profile-loaded"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    fake_dotdrop = helper_dir / "dotdrop"
    fake_dotdrop.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_dotdrop.chmod(0o755)

    fake_uv = helper_dir / "uv"
    fake_uv.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'printf \'%s\\n\' "$@" > "$DOTMAN_UV_ARGS_FILE"',
                'printf \'%s\\n\' "$DOTMAN_WRAPPER_VALUE" > "$DOTMAN_WRAPPER_MARKER"',
                "exit 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    env = build_isolated_dotman_env(tmp_path)
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTMAN_UV_ARGS_FILE"] = str(args_file)

    result = subprocess.run(
        [str(dotman_path), "install", "-f", "-p", "repro", "-c", str(config_path)],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert marker_file.read_text(encoding="utf-8").strip() == "repo-profile-loaded"
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "run",
        "--project",
        str(repo_root),
        str(script_path),
        "install",
        "-f",
        "-p",
        "repro",
        "-c",
        str(config_path),
    ]


def test_install_force_skips_whole_profile_confirmation(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    result = run_dotman(config_path, "install", "-f", "-p", "repro")

    assert result.returncode == 0
    assert 'Install all dotfiles for profile "repro" [y/N] ?' not in (result.stdout + result.stderr)
    assert "1 file(s) processed, 1 updated, 0 failed" in result.stdout
    assert (live_dir / "settings.toml").read_text(encoding="utf-8") == (
        repo_source_dir / "settings.toml"
    ).read_text(encoding="utf-8")
    assert (live_dir / "extra.toml").exists()


def test_install_remove_existing_deletes_unmanaged_directory_children(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    result = run_dotman(config_path, "install", "-R", "-f", "-p", "repro")

    assert result.returncode == 0
    assert (live_dir / "settings.toml").read_text(encoding="utf-8") == (
        repo_source_dir / "settings.toml"
    ).read_text(encoding="utf-8")
    assert not (live_dir / "extra.toml").exists()


def test_install_remove_existing_preflight_skips_clean_privileged_phase(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    env, dotdrop_args_file, sudo_args_file, phase_runs_file = create_fake_dotdrop_tools(
        tmp_path,
        repo_source_dir=repo_source_dir,
        live_dir=live_dir,
        compare_output="1 dotfile(s) compared.",
        install_dry_output="[DRY] would install clean target\n\n1 dotfile(s) installed.",
    )

    (live_dir / "settings.toml").write_text(
        (repo_source_dir / "settings.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (live_dir / "extra.toml").unlink()
    live_dir.chmod(0o555)
    (live_dir / "settings.toml").chmod(0o444)

    try:
        result = run_dotman(config_path, "install", "-R", "-f", "-p", "repro", extra_env=env)

        assert result.returncode == 0
        assert "1 file(s) processed, 0 updated, 0 failed" in result.stdout
        assert "compare" in dotdrop_args_file.read_text(encoding="utf-8")
        assert "install" in dotdrop_args_file.read_text(encoding="utf-8")
        assert not sudo_args_file.exists()
        assert not phase_runs_file.exists()
    finally:
        (live_dir / "settings.toml").chmod(0o644)
        live_dir.chmod(0o755)


def test_install_remove_existing_preflight_runs_privileged_phase_for_removals(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    env, _dotdrop_args_file, sudo_args_file, phase_runs_file = create_fake_dotdrop_tools(
        tmp_path,
        repo_source_dir=repo_source_dir,
        live_dir=live_dir,
        compare_output="1 dotfile(s) compared.",
        install_dry_output=(
            f"[DRY] would remove {live_dir / 'extra.toml'}\n\n1 dotfile(s) installed."
        ),
    )

    live_dir.chmod(0o555)
    (live_dir / "settings.toml").chmod(0o444)

    try:
        result = run_dotman(config_path, "install", "-R", "-f", "-p", "repro", extra_env=env)

        assert result.returncode == 0
        assert sudo_args_file.exists()
        assert phase_runs_file.read_text(encoding="utf-8") == "install\n"
    finally:
        (live_dir / "settings.toml").chmod(0o644)
        live_dir.chmod(0o755)


def test_install_phase_need_run_ignores_whitespace_prefixed_compare_logs(tmp_path: Path, monkeypatch) -> None:
    manager = DotManager(["install"])
    manager.dotdrop_cmd = "dotdrop"
    manager.operation = "install"
    manager.parsed = DOTMAN_MODULE.ParsedArgs(base_args=["--profile=repro"])
    manager.resolved_profile = "repro"
    manager.normalized_destination_by_key = {"f_config": "/root/.config/example.toml"}

    compare_completed = subprocess.CompletedProcess(
        ["dotdrop", "compare"],
        0,
        "",
        '\t-> executing "uv run scripts/toml_transform.py repo.toml repo.toml.trans"\n'
        "\n1 dotfile(s) compared.\n",
    )

    dry_run_completed = subprocess.CompletedProcess(
        ["dotdrop", "install", "-d"],
        0,
        "",
        "",
    )

    run_results = [compare_completed, dry_run_completed]

    def fake_run(*_args, **_kwargs):
        return run_results.pop(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert manager.install_phase_need_run(["f_config"]) is False


def test_install_phase_need_run_keeps_multiple_compare_targets(tmp_path: Path, monkeypatch) -> None:
    manager = DotManager(["install"])
    manager.dotdrop_cmd = "dotdrop"
    manager.operation = "install"
    manager.parsed = DOTMAN_MODULE.ParsedArgs(base_args=["--profile=repro"])
    manager.resolved_profile = "repro"
    manager.normalized_destination_by_key = {
        "f_config": "/root/.config/example.toml",
        "f_other": "/root/.config/other.toml",
    }

    recorded_commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        recorded_commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "", "1 dotfile(s) compared.\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert manager.install_phase_need_run(["f_config", "f_other"]) is False
    assert recorded_commands == [
        [
            "dotdrop",
            "compare",
            "-L",
            "-b",
            "--profile=repro",
            "-C",
            "/root/.config/example.toml",
            "-C",
            "/root/.config/other.toml",
        ]
    ]


def test_no_action_is_delegated_to_dotdrop_unchanged(tmp_path: Path) -> None:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    args_file = tmp_path / "dotdrop-args.txt"
    fake_dotdrop = helper_dir / "dotdrop"
    fake_dotdrop.write_text(
        """#!/usr/bin/env bash
if (( $# > 0 )); then
  printf '%s\n' "$@" > "$DOTDROP_ARGS_FILE"
else
  : > "$DOTDROP_ARGS_FILE"
fi
""",
        encoding="utf-8",
    )
    fake_dotdrop.chmod(0o755)
    write_fake_uv_runner(helper_dir)

    env = build_isolated_dotman_env(tmp_path)
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_CONFIG"] = str(REPO_ROOT / "config.yaml")
    env["DOTDROP_ARGS_FILE"] = str(args_file)

    result = subprocess.run(
        [str(DOTMAN_PATH)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert args_file.read_text(encoding="utf-8") == ""


def test_leading_option_passthrough_keeps_explicit_profile_with_metadata(tmp_path: Path) -> None:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    args_file = tmp_path / "dotdrop-args.txt"
    fake_dotdrop = helper_dir / "dotdrop"
    fake_dotdrop.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" > "$DOTDROP_ARGS_FILE"
""",
        encoding="utf-8",
    )
    fake_dotdrop.chmod(0o755)
    write_fake_uv_runner(helper_dir)

    env = build_isolated_dotman_env(tmp_path)
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_CONFIG"] = str(REPO_ROOT / "config.yaml")
    env["DOTDROP_ARGS_FILE"] = str(args_file)

    result = subprocess.run(
        [str(DOTMAN_PATH), "--profile", "repro"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "--profile=repro",
        f"--cfg={REPO_ROOT / 'config.yaml'}",
    ]


def test_python_entrypoint_reports_missing_dotdrop(tmp_path: Path) -> None:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()

    env = build_isolated_dotman_env(tmp_path)
    env["PATH"] = str(helper_dir)

    result = subprocess.run(
        [sys.executable, str(DOTMAN_PY_PATH)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 127
    assert "dotdrop not found in PATH" in result.stderr


def test_run_operation_exits_cleanly_on_interrupt(monkeypatch, capsys) -> None:
    manager = DotManager(["install"])
    manager.dotdrop_cmd = "dotdrop"
    manager.operation = "install"
    manager.parsed.base_args = []

    monkeypatch.setattr(manager, "run_streaming_subprocess", lambda _command: (_ for _ in ()).throw(KeyboardInterrupt()))

    with pytest.raises(SystemExit) as exc_info:
        manager.run_operation_for_targets(False, ["d_app"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 130
    assert "interrupted" in captured.err


def test_streaming_output_flushes_prompt_without_newline() -> None:
    stream = io.StringIO()

    remainder = DotManager.write_stream_chunks('Overwrite "/tmp/example" [y/N] ? ', stream=stream)

    assert remainder == ""
    assert stream.getvalue() == 'Overwrite "/tmp/example" [y/N] ? '


def test_run_operation_cleans_stale_transform_output(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "repo" / "config.toml"
    transient_path = tmp_path / "repo" / "config.toml.trans"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("source\n", encoding="utf-8")
    transient_path.write_text("stale\n", encoding="utf-8")

    manager = DotManager(["install"])
    manager.dotdrop_cmd = "dotdrop"
    manager.operation = "install"
    manager.parsed.base_args = []
    manager.source_by_key = {"f_config": str(source_path)}

    monkeypatch.setattr(
        manager,
        "run_streaming_subprocess",
        lambda _command: subprocess.CompletedProcess(_command, 0, "", ""),
    )

    manager.run_operation_for_targets(False, ["f_config"])

    assert not transient_path.exists()


def test_update_operation_counts_only_actual_changed_files_from_dry_run(monkeypatch) -> None:
    manager = DotManager(["update"])
    manager.dotdrop_cmd = "dotdrop"
    manager.operation = "update"
    manager.parsed.base_args = ["--profile=repro"]

    dry_run_completed = subprocess.CompletedProcess(
        ["dotdrop", "update", "-d"],
        0,
        "\n".join(
            [
                "[DRY] would update content of /repo/settings.toml from /live/settings.toml",
                "[DRY] would cp /live/extra.toml /repo/extra.toml",
                "",
            ]
        ),
        "",
    )

    def fake_run(command, **kwargs):
        assert command == [
            "dotdrop",
            "update",
            "-b",
            "-d",
            "--profile=repro",
            "-f",
            "-k",
            "d_app",
        ]
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return dry_run_completed

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        manager,
        "run_streaming_subprocess",
        lambda _command: subprocess.CompletedProcess(_command, 0, "1 file(s) updated.\n", ""),
    )

    result = manager.run_operation_for_targets(False, ["d_app"])

    assert result.exit_code == 0
    assert result.changed_count == 2


def test_update_operation_falls_back_to_dotdrop_summary_when_dry_run_fails(monkeypatch) -> None:
    manager = DotManager(["update"])
    manager.dotdrop_cmd = "dotdrop"
    manager.operation = "update"
    manager.parsed.base_args = []

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["dotdrop", "update", "-d"], 2, "", "preview failed"),
    )
    monkeypatch.setattr(
        manager,
        "run_streaming_subprocess",
        lambda _command: subprocess.CompletedProcess(_command, 0, "3 file(s) updated.\n", ""),
    )

    result = manager.run_operation_for_targets(False, ["d_app", "d_other", "d_third"])

    assert result.exit_code == 0
    assert result.changed_count == 3


def test_template_update_can_be_skipped_interactively(tmp_path: Path) -> None:
    config_path, repo_source_path, live_path = create_template_repro_project(tmp_path)
    original_source = repo_source_path.read_text(encoding="utf-8")

    exit_code, output = run_interactive_dotman(config_path, live_path, "n")

    assert exit_code == 0
    assert 'overwrite template file "' in output
    assert 'profile" [y/N] ?' in output
    assert "skipped template update: key=f_profile" in output
    assert repo_source_path.read_text(encoding="utf-8") == original_source


def test_template_update_can_be_confirmed_interactively(tmp_path: Path) -> None:
    config_path, repo_source_path, live_path = create_template_repro_project(tmp_path)

    exit_code, output = run_interactive_dotman(config_path, live_path, "y")

    assert exit_code == 0
    assert 'overwrite template file "' in output
    assert repo_source_path.read_text(encoding="utf-8") == """start
{%@@ if os == \"linux\" @@%}
live
{%@@ endif @@%}
end
"""


def test_unchanged_template_update_skips_prompt(tmp_path: Path) -> None:
    config_path, repo_source_path, live_path = create_template_repro_project(tmp_path)
    live_path.write_text("start\nrepo\nend\n", encoding="utf-8")

    exit_code, output = run_interactive_dotman(config_path, live_path, "y")

    assert exit_code == 0
    assert 'overwrite template file "' not in output
    assert repo_source_path.read_text(encoding="utf-8") == """start
{%@@ if os == \"linux\" @@%}
repo
{%@@ endif @@%}
end
"""


def test_template_update_is_skipped_for_dotdrop_include_sources(tmp_path: Path) -> None:
    config_path, repo_source_path, live_path = create_template_repro_project(
        tmp_path,
        with_include_directive=True,
    )
    original_source = repo_source_path.read_text(encoding="utf-8")

    result = run_dotman(config_path, "update", "-p", "repro", str(live_path))

    assert result.returncode == 0
    assert 'overwrite template file "' not in (result.stdout + result.stderr)
    assert "skipped template-aware update: key=f_profile" in result.stdout
    assert "reason=dotdrop include directives are not supported" in result.stdout
    assert repo_source_path.read_text(encoding="utf-8") == original_source

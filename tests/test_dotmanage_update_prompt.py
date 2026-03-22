from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import pty
import pytest
import select
import shutil
import socket
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DOTMANAGE_PATH = REPO_ROOT / "dotfiles" / "bin" / "dotmanage"
DOTMANAGE_PY_PATH = REPO_ROOT / "scripts" / "dotmanage.py"

DOTMANAGE_SPEC = importlib.util.spec_from_file_location("dotmanage_py", DOTMANAGE_PY_PATH)
assert DOTMANAGE_SPEC is not None
assert DOTMANAGE_SPEC.loader is not None
DOTMANAGE_MODULE = importlib.util.module_from_spec(DOTMANAGE_SPEC)
sys.modules[DOTMANAGE_SPEC.name] = DOTMANAGE_MODULE
DOTMANAGE_SPEC.loader.exec_module(DOTMANAGE_MODULE)
DotManager = DOTMANAGE_MODULE.DotManager


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


def run_interactive_dotmanage(
    config_path: Path,
    target_path: Path | None,
    answer: str,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["DOTDROP_CONFIG"] = str(config_path)

    command_parts = [
        str(DOTMANAGE_PATH),
        "update",
        "-p",
        "repro",
    ]
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


def run_dotmanage(
    config_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DOTDROP_CONFIG"] = str(config_path)
    if extra_env is not None:
        env.update(extra_env)

    return subprocess.run(
        [str(DOTMANAGE_PATH), *args],
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
                'exec python3 "$@"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

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

    exit_code, output = run_interactive_dotmanage(config_path, live_dir, "n\nn")

    assert exit_code == 0
    assert output.count('overwrite dotfiles path "') == 1
    assert output.count('import live path into dotfiles "') == 1
    assert 'overwrite dotfiles path "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'
    assert not (repo_source_dir / "extra.toml").exists()


def test_declined_update_backup_skips_live_socket_entries(tmp_path: Path) -> None:
    short_root = Path(tempfile.mkdtemp(prefix="dotmanage-", dir="/tmp"))
    source_path = short_root / "repo" / "agent"
    live_path = short_root / "home" / ".ssh" / "agent"
    source_path.mkdir(parents=True)
    live_path.mkdir(parents=True)

    (source_path / "tracked").write_text("repo\n", encoding="utf-8")
    (live_path / "tracked").write_text("live\n", encoding="utf-8")

    socket_path = live_path / "agent.sock"
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(socket_path))

    manager = DotManager(["update"])
    try:
        manager.backup_declined_update_path(source_path, live_path)

        assert (source_path / "tracked").read_text(encoding="utf-8") == "live\n"
        assert not (source_path / "agent.sock").exists()

        manager.restore_declined_update_state()
        assert (source_path / "tracked").read_text(encoding="utf-8") == "repo\n"
        assert manager.declined_update_backup_dir is None
    finally:
        server.close()
        shutil.rmtree(short_root)


def test_directory_update_can_be_confirmed_interactively(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, live_dir, "y\ny")

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

    exit_code, output = run_interactive_dotmanage(config_path, live_dir, "y\nn\ny")

    assert exit_code == 0
    assert 'overwrite dotfiles path "' in output
    assert 'import live path into dotfiles "' in output
    assert 'live-only.toml' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'
    assert not (repo_source_dir / "live-only.toml").exists()


def test_whole_profile_update_prompts_and_skips_tracked_child_file(tmp_path: Path) -> None:
    config_path, repo_source_dir, _live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, None, "y\nn\nn")

    assert exit_code == 0
    assert 'Update all dotfiles for profile "repro" [y/N] ?' in output
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

    exit_code, output = run_interactive_dotmanage(config_path, live_file, "y")

    assert exit_code == 0
    assert output.count('overwrite dotfiles path "') == 1
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert repo_other.read_text(encoding="utf-8") == 'value = "repo other"\n'
    assert not (repo_source_dir / "live-only.toml").exists()


def test_unmatched_update_path_is_rejected(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    unmatched_path = live_dir.parent / "missing" / "settings.toml"

    exit_code, output = run_interactive_dotmanage(config_path, unmatched_path, "y")

    assert exit_code == 2
    assert "no tracked dotdrop key matches update target" in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'


def test_unknown_command_is_delegated_to_dotdrop_unchanged(tmp_path: Path) -> None:
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

    env = os.environ.copy()
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_ARGS_FILE"] = str(args_file)
    env["DOTDROP_EXIT_CODE"] = "23"

    result = subprocess.run(
        [str(DOTMANAGE_PATH), "compare", "--profile", "repro", "d_app"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 23
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "compare",
        "--profile",
        "repro",
        "d_app",
    ]


def test_wrapper_sources_repo_core_env_before_running_uv(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    helper_dir = tmp_path / "bin"
    dotmanage_path = repo_root / "dotfiles" / "bin" / "dotmanage"
    core_env_path = repo_root / "dotfiles" / "env.core.sh"
    config_path = repo_root / "config.yaml"
    script_path = repo_root / "scripts" / "dotmanage.py"
    marker_file = tmp_path / "marker.txt"
    args_file = tmp_path / "uv-args.txt"

    helper_dir.mkdir()
    dotmanage_path.parent.mkdir(parents=True)
    script_path.parent.mkdir(parents=True)
    core_env_path.parent.mkdir(parents=True, exist_ok=True)

    dotmanage_path.write_text(DOTMANAGE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    dotmanage_path.chmod(0o755)
    config_path.write_text("config:\n  dotpath: dotfiles\n", encoding="utf-8")
    script_path.write_text("print('placeholder')\n", encoding="utf-8")
    core_env_path.write_text(
        "\n".join(
            [
                f'export DOTMANAGE_WRAPPER_MARKER="{marker_file}"',
                'export DOTMANAGE_WRAPPER_VALUE="repo-profile-loaded"',
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
                'printf \'%s\\n\' \"$@\" > \"$DOTMANAGE_UV_ARGS_FILE\"',
                'printf \'%s\\n\' \"$DOTMANAGE_WRAPPER_VALUE\" > \"$DOTMANAGE_WRAPPER_MARKER\"',
                "exit 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTMANAGE_UV_ARGS_FILE"] = str(args_file)

    result = subprocess.run(
        [str(dotmanage_path), "install", "-f", "-p", "repro", "-c", str(config_path)],
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

    result = run_dotmanage(config_path, "install", "-f", "-p", "repro")

    assert result.returncode == 0
    assert 'Install all dotfiles for profile "repro" [y/N] ?' not in (result.stdout + result.stderr)
    assert "1 file(s) processed, 1 updated, 0 failed" in result.stdout
    assert (live_dir / "settings.toml").read_text(encoding="utf-8") == (
        repo_source_dir / "settings.toml"
    ).read_text(encoding="utf-8")
    assert (live_dir / "extra.toml").exists()


def test_install_remove_existing_deletes_unmanaged_directory_children(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    result = run_dotmanage(config_path, "install", "-R", "-f", "-p", "repro")

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
        result = run_dotmanage(config_path, "install", "-R", "-f", "-p", "repro", extra_env=env)

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
        result = run_dotmanage(config_path, "install", "-R", "-f", "-p", "repro", extra_env=env)

        assert result.returncode == 0
        assert sudo_args_file.exists()
        assert phase_runs_file.read_text(encoding="utf-8") == "install\n"
    finally:
        (live_dir / "settings.toml").chmod(0o644)
        live_dir.chmod(0o755)


def test_system_phase_needs_run_ignores_whitespace_prefixed_compare_logs(tmp_path: Path, monkeypatch) -> None:
    manager = DotManager(["install"])
    manager.dotdrop_cmd = "dotdrop"
    manager.operation = "install"
    manager.parsed = DOTMANAGE_MODULE.ParsedArgs(files_args=["-p", "repro"], base_args=["-p", "repro"])
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

    assert manager.system_phase_needs_run(["f_config"]) is False


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

    env = os.environ.copy()
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_ARGS_FILE"] = str(args_file)

    result = subprocess.run(
        [str(DOTMANAGE_PATH)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert args_file.read_text(encoding="utf-8") == ""


def test_leading_option_without_action_is_delegated_to_dotdrop_unchanged(tmp_path: Path) -> None:
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

    env = os.environ.copy()
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    env["DOTDROP_ARGS_FILE"] = str(args_file)

    result = subprocess.run(
        [str(DOTMANAGE_PATH), "--profile", "repro"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "--profile",
        "repro",
    ]


def test_python_entrypoint_reports_missing_dotdrop(tmp_path: Path) -> None:
    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    uv_path = shutil.which("uv")
    assert uv_path is not None

    env = os.environ.copy()
    env["PATH"] = str(helper_dir)

    result = subprocess.run(
        [uv_path, "run", str(DOTMANAGE_PY_PATH)],
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


def test_template_update_can_be_skipped_interactively(tmp_path: Path) -> None:
    config_path, repo_source_path, live_path = create_template_repro_project(tmp_path)
    original_source = repo_source_path.read_text(encoding="utf-8")

    exit_code, output = run_interactive_dotmanage(config_path, live_path, "n")

    assert exit_code == 0
    assert 'overwrite template file "' in output
    assert 'profile" [y/N] ?' in output
    assert "skipped template update: key=f_profile" in output
    assert repo_source_path.read_text(encoding="utf-8") == original_source


def test_template_update_can_be_confirmed_interactively(tmp_path: Path) -> None:
    config_path, repo_source_path, live_path = create_template_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, live_path, "y")

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

    exit_code, output = run_interactive_dotmanage(config_path, live_path, "y")

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

    result = run_dotmanage(config_path, "update", "-p", "repro", str(live_path))

    assert result.returncode == 0
    assert 'overwrite template file "' not in (result.stdout + result.stderr)
    assert "skipped template-aware update: key=f_profile" in result.stdout
    assert "reason=dotdrop include directives are not supported" in result.stdout
    assert repo_source_path.read_text(encoding="utf-8") == original_source

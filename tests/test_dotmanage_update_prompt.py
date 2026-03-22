from __future__ import annotations

import os
from pathlib import Path
import pty
import select
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
DOTMANAGE_PATH = REPO_ROOT / "dotfiles" / "bin" / "dotmanage"


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


def create_template_repro_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "dotdrop-template-repro"
    repo_source_path = repo_root / "dotfiles" / "profile"
    live_path = tmp_path / "home" / ".profile"
    workdir = tmp_path / "workdir"
    helper_dir = repo_root / "scripts"

    repo_source_path.parent.mkdir(parents=True)
    live_path.parent.mkdir(parents=True)
    workdir.mkdir()
    helper_dir.mkdir()
    (helper_dir / "dotdrop_template_update.py").symlink_to(
        REPO_ROOT / "scripts" / "dotdrop_template_update.py"
    )

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

    repo_source_path.write_text(
        """start
{%@@ if os == \"linux\" @@%}
repo
{%@@ endif @@%}
end
""",
        encoding="utf-8",
    )
    live_path.write_text("start\nlive\nend\n", encoding="utf-8")

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
    assert output.count('overwrite dotfiles file "') == 1
    assert output.count('import live file into dotfiles "') == 1
    assert 'overwrite dotfiles file "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'
    assert not (repo_source_dir / "extra.toml").exists()


def test_directory_update_can_be_confirmed_interactively(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, live_dir, "y\ny")

    assert exit_code == 0
    assert 'overwrite dotfiles file "' in output
    assert 'import live file into dotfiles "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'


def test_directory_update_prompts_before_importing_live_only_file(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    live_only = live_dir / "live-only.toml"

    live_only.write_text('value = "live only"\n', encoding="utf-8")

    exit_code, output = run_interactive_dotmanage(config_path, live_dir, "y\nn\ny")

    assert exit_code == 0
    assert 'overwrite dotfiles file "' in output
    assert 'import live file into dotfiles "' in output
    assert 'live-only.toml' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'
    assert not (repo_source_dir / "live-only.toml").exists()


def test_whole_profile_update_prompts_and_skips_tracked_child_file(tmp_path: Path) -> None:
    config_path, repo_source_dir, _live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, None, "y\nn\nn")

    assert exit_code == 0
    assert 'Update all dotfiles for profile "repro" [y/N] ?' in output
    assert 'import live file into dotfiles "' in output
    assert 'overwrite dotfiles file "' in output
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
    assert output.count('overwrite dotfiles file "') == 1
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


def test_install_force_skips_whole_profile_confirmation(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    result = run_dotmanage(config_path, "install", "-f", "-p", "repro")

    assert result.returncode == 0
    assert 'Install all dotfiles for profile "repro" [y/N] ?' not in (result.stdout + result.stderr)
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
        assert "0 installed" in result.stdout
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

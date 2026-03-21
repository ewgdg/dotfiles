from __future__ import annotations

import os
from pathlib import Path
import shlex
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


def run_interactive_dotmanage(
    config_path: Path,
    target_path: Path | None,
    answer: str,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["DOTDROP_CONFIG"] = str(config_path)

    command_parts = [
        shlex.quote(str(DOTMANAGE_PATH)),
        "update",
        "-p",
        "repro",
    ]
    if target_path is not None:
        command_parts.append(shlex.quote(str(target_path)))

    command = " ".join(
        [
            "printf",
            shlex.quote(f"{answer}\\n"),
            "|",
            "script",
            "-qec",
            shlex.quote(" ".join(command_parts)),
            "/dev/null",
        ]
    )

    result = subprocess.run(
        ["bash", "-lc", command],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    return result.returncode, result.stdout + result.stderr


def test_directory_update_can_be_skipped_interactively(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, live_dir, "n")

    assert exit_code == 0
    assert output.count('overwrite dotfiles file "') == 1
    assert 'overwrite dotfiles file "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'


def test_directory_update_can_be_confirmed_interactively(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, live_dir, "y")

    assert exit_code == 0
    assert 'overwrite dotfiles file "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'

def test_whole_profile_update_prompts_and_skips_tracked_child_file(tmp_path: Path) -> None:
    config_path, repo_source_dir, _live_dir = create_repro_project(tmp_path)

    exit_code, output = run_interactive_dotmanage(config_path, None, "y\nn")

    assert exit_code == 0
    assert 'Update all dotfiles for profile "repro" [y/N] ?' in output
    assert 'overwrite dotfiles file "' in output
    assert 'settings.toml" [y/N] ?' in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'
    assert (repo_source_dir / "extra.toml").read_text(encoding="utf-8") == 'value = "extra"\n'

def test_child_path_update_promotes_to_parent_key(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    live_file = live_dir / "settings.toml"
    repo_other = repo_source_dir / "other.toml"
    live_other = live_dir / "other.toml"

    repo_other.write_text('value = "repo other"\n', encoding="utf-8")
    live_other.write_text('value = "live other"\n', encoding="utf-8")

    exit_code, output = run_interactive_dotmanage(config_path, live_file, "y\ny")

    assert exit_code == 0
    assert output.count('overwrite dotfiles file "') == 2
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "live"\n'
    assert repo_other.read_text(encoding="utf-8") == 'value = "live other"\n'


def test_unmatched_update_path_is_rejected(tmp_path: Path) -> None:
    config_path, repo_source_dir, live_dir = create_repro_project(tmp_path)
    unmatched_path = live_dir.parent / "missing" / "settings.toml"

    exit_code, output = run_interactive_dotmanage(config_path, unmatched_path, "y")

    assert exit_code == 2
    assert "no tracked dotdrop key matches update target" in output
    assert (repo_source_dir / "settings.toml").read_text(encoding="utf-8") == 'value = "repo"\n'
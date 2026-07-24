from __future__ import annotations

from pathlib import Path
import os
import stat
import subprocess
import tomllib
import shutil


REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DOTMAN_ROOT = Path(os.environ.get("DOTMAN_CANDIDATE_ROOT", REPO_ROOT.parent / "dotman"))
UV_EXECUTABLE = shutil.which("uv")


def write_fake_uv(fake_bin: Path, default_tool_bin: Path, log_path: Path) -> None:
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        f"""#!/usr/bin/env sh
set -eu

tool_bin="${{UV_TOOL_BIN_DIR:-${{XDG_BIN_HOME:-{str(default_tool_bin)}}}}}"

if [ "$1" = "tool" ] && [ "$2" = "dir" ] && [ "$3" = "--bin" ]; then
  printf '%s\n' "$tool_bin"
  exit 0
fi

if [ "$1" = "tool" ] && [ "$2" = "install" ]; then
  printf 'install:%s\n' "$*" >> {str(log_path)!r}
  mkdir -p "$tool_bin"
  cat > "$tool_bin/dotman" <<'EOF'
#!/usr/bin/env sh
set -eu
printf 'dotman:%s\n' "$*" >> {str(log_path)!r}
if [ "$1" = "transform" ] && [ "$2" = "toml" ]; then
  exec {UV_EXECUTABLE!r} run --project {str(CANDIDATE_DOTMAN_ROOT)!r} dotman "$@"
fi
printf 'unexpected dotman args: %s\n' "$*" >&2
exit 2
EOF
  chmod +x "$tool_bin/dotman"
  exit 0
fi

if [ "$1" = "run" ]; then
  shift
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --no-project)
        shift
        ;;
      --with)
        shift 2
        ;;
      *)
        break
        ;;
    esac
  done
  if [ "$1" = "python" ]; then
    shift
    exec python "$@"
  fi
  exec "$@"
fi

printf 'unexpected uv args: %s\n' "$*" >&2
exit 2
""",
        encoding="utf-8",
    )
    fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IXUSR)


def test_init_installs_dotman_manager_config_with_toml_merge(tmp_path: Path) -> None:
    home = tmp_path / "home"
    xdg_config_home = tmp_path / "xdg-config"
    fake_bin = tmp_path / "bin"
    uv_log_path = tmp_path / "uv-tool.log"
    fake_bin.mkdir()
    home.mkdir()
    write_fake_uv(fake_bin, home / ".local" / "bin", uv_log_path)

    config_path = xdg_config_home / "dotman" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
[repos.main]
path = "~/old-dotfiles"
order = 99
state_key = "old-main"

[repos.extra]
path = "~/extra"
order = 20
state_key = "extra"

[symlinks]
file_symlink_mode = "prompt"
dir_symlink_mode = "follow"
""".lstrip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(xdg_config_home),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "TMPDIR": str(tmp_path),
            "DOTMAN_TOOL_SPEC": "file:///tmp/fake-dotman",
        }
    )

    completed = subprocess.run(
        ["sh", "init.sh"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    main_repo = config["repos"]["main"]
    assert Path(main_repo["path"]).samefile(REPO_ROOT)
    assert main_repo == {
        "path": main_repo["path"],
        "order": 10,
        "state_key": "main",
    }
    assert config["repos"]["extra"] == {
        "path": "~/extra",
        "order": 20,
        "state_key": "extra",
    }
    assert config["ui"] == {"compact_path_tail_segments": 3}
    assert config["symlinks"] == {
        "file_symlink_mode": "prompt",
        "dir_symlink_mode": "follow",
    }
    events = uv_log_path.read_text(encoding="utf-8").splitlines()
    assert events[0] == "install:tool install --upgrade file:///tmp/fake-dotman"
    assert events[1].startswith(f"dotman:transform toml {config_path} {config_path} --mode merge ")
    assert "--selector-type remove --selectors repos.main" in events[1]
    assert events[1].endswith(f"--compare-file {config_path}")
    assert f"installing dotman manager config at {config_path}" in completed.stderr


def test_init_upgrades_dotman_before_first_transform(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    event_log = tmp_path / "events.log"
    fake_bin.mkdir()
    home.mkdir()
    (fake_bin / "dotman").write_text(
        f"#!/usr/bin/env sh\nprintf 'stale-dotman:%s\\n' \"$*\" >> {str(event_log)!r}\nexit 9\n",
        encoding="utf-8",
    )
    (fake_bin / "dotman").chmod(0o755)
    write_fake_uv(fake_bin, home / ".local" / "bin", event_log)

    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "PATH": f"{fake_bin}:{home / '.local' / 'bin'}:{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "DOTMAN_TOOL_SPEC": "candidate-dotman",
    }
    subprocess.run(["sh", "init.sh"], cwd=REPO_ROOT, env=env, check=True, capture_output=True)

    events = event_log.read_text(encoding="utf-8").splitlines()
    assert events[0] == "install:tool install --upgrade candidate-dotman"
    assert events[1].startswith("dotman:transform toml ")
    assert not any(event.startswith("stale-dotman:") for event in events)


def test_init_uses_custom_uv_tool_bin_on_first_run(tmp_path: Path) -> None:
    for environment_variable in ("UV_TOOL_BIN_DIR", "XDG_BIN_HOME"):
        case_root = tmp_path / environment_variable.lower()
        home = case_root / "home"
        fake_bin = case_root / "path-bin"
        custom_tool_bin = case_root / "custom-tool-bin"
        event_log = case_root / "events.log"
        fake_bin.mkdir(parents=True)
        home.mkdir()
        write_fake_uv(fake_bin, home / ".local" / "bin", event_log)

        env = {
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(case_root / "config"),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "TMPDIR": str(case_root),
            "DOTMAN_TOOL_SPEC": "candidate-dotman",
            environment_variable: str(custom_tool_bin),
        }
        other_variable = "XDG_BIN_HOME" if environment_variable == "UV_TOOL_BIN_DIR" else "UV_TOOL_BIN_DIR"
        env.pop(other_variable, None)

        subprocess.run(["sh", "init.sh"], cwd=REPO_ROOT, env=env, check=True, capture_output=True)

        events = event_log.read_text(encoding="utf-8").splitlines()
        assert events[0] == "install:tool install --upgrade candidate-dotman"
        assert events[1].startswith("dotman:transform toml ")
        assert (custom_tool_bin / "dotman").is_file()


def test_init_fails_clearly_when_uv_does_not_install_dotman_executable(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    missing_tool_bin = tmp_path / "missing-tool-bin"
    fake_bin.mkdir()
    home.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        f"""#!/usr/bin/env sh
if [ "$1 $2" = "tool install" ]; then exit 0; fi
if [ "$1 $2 $3" = "tool dir --bin" ]; then printf '%s\\n' {str(missing_tool_bin)}; exit 0; fi
exit 2
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOTMAN_TOOL_SPEC": "candidate-dotman",
    }

    completed = subprocess.run(["sh", "init.sh"], cwd=REPO_ROOT, env=env, text=True, capture_output=True)

    assert completed.returncode == 1
    assert f"dotman executable not found after install: {missing_tool_bin}/dotman" in completed.stderr


def test_init_fills_only_missing_dotman_manager_defaults(tmp_path: Path) -> None:
    home = tmp_path / "home"
    xdg_config_home = tmp_path / "xdg-config"
    fake_bin = tmp_path / "bin"
    uv_log_path = tmp_path / "uv-tool.log"
    fake_bin.mkdir()
    home.mkdir()
    write_fake_uv(fake_bin, home / ".local" / "bin", uv_log_path)

    config_path = xdg_config_home / "dotman" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
[ui]
compact_path_tail_segments = 7

[symlinks]
file_symlink_mode = "relative"
""".lstrip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(xdg_config_home),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "TMPDIR": str(tmp_path),
            "DOTMAN_TOOL_SPEC": "file:///tmp/fake-dotman",
        }
    )

    subprocess.run(
        ["sh", "init.sh"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["ui"] == {"compact_path_tail_segments": 7}
    assert config["symlinks"] == {
        "file_symlink_mode": "relative",
        "dir_symlink_mode": "follow",
    }

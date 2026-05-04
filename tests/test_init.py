from __future__ import annotations

from pathlib import Path
import os
import stat
import subprocess
import sys
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_fake_uv(fake_bin: Path, log_path: Path) -> None:
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        f"""#!/usr/bin/env sh
set -eu

if [ "$1" = "tool" ] && [ "$2" = "install" ]; then
  printf '%s\n' "$*" >> {str(log_path)!r}
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
    exec {str(sys.executable)!r} "$@"
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
    write_fake_uv(fake_bin, uv_log_path)

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
    assert config["repos"]["main"] == {
        "path": str(REPO_ROOT),
        "order": 10,
        "state_key": "main",
    }
    assert config["repos"]["extra"] == {
        "path": "~/extra",
        "order": 20,
        "state_key": "extra",
    }
    assert config["symlinks"] == {
        "file_symlink_mode": "prompt",
        "dir_symlink_mode": "follow",
    }
    assert "tool install --upgrade file:///tmp/fake-dotman" in uv_log_path.read_text(
        encoding="utf-8"
    )
    assert f"installing dotman manager config at {config_path}" in completed.stderr

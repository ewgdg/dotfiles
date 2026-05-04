#!/usr/bin/env sh
set -eu

log() {
  printf '%s\n' "$*" >&2
}

die() {
  log "$*"
  exit 1
}

script_dir="$(
  cd -- "$(dirname -- "$0")" >/dev/null 2>&1
  pwd -P
)"
repo_root="${script_dir}"
default_uv_bin_dir="${HOME}/.local/bin"
dotman_tool_spec_default='git+https://github.com/ewgdg/dotman.git'
dotman_tool_spec="${DOTMAN_TOOL_SPEC:-$dotman_tool_spec_default}"
dotman_manager_repo_name="${DOTFILES_DOTMAN_MANAGER_REPO_NAME:-main}"
dotman_config_overlay_path=""
uv_installer_script_path=""

cleanup() {
  if [ -n "${uv_installer_script_path}" ]; then
    rm -f "${uv_installer_script_path}"
  fi
  if [ -n "${dotman_config_overlay_path}" ]; then
    rm -f "${dotman_config_overlay_path}"
  fi
}

trap cleanup EXIT HUP INT TERM

if [ "$#" -gt 0 ]; then
  die "init.sh only installs dependencies; it takes no arguments"
fi

prepend_path() {
  case ":${PATH:-}:" in
    *":$1:"*) ;;
    *)
      if [ -n "${PATH:-}" ]; then
        PATH="$1:${PATH}"
      else
        PATH="$1"
      fi
      ;;
  esac
}

run_installer_script() {
  uv_installer_script_path="$(mktemp "${TMPDIR:-/tmp}/uv-install.XXXXXX.sh")"

  curl --proto '=https' -LsSf https://astral.sh/uv/install.sh -o "${uv_installer_script_path}"
  env UV_UNMANAGED_INSTALL="${default_uv_bin_dir}" UV_NO_MODIFY_PATH=1 sh "${uv_installer_script_path}"
}

dotman_config_path() {
  if [ -n "${XDG_CONFIG_HOME:-}" ]; then
    printf '%s/dotman/config.toml\n' "${XDG_CONFIG_HOME}"
    return 0
  fi

  printf '%s/.config/dotman/config.toml\n' "${HOME}"
}

generate_dotman_config_overlay() {
  DOTFILES_DOTMAN_REPO_ROOT="${repo_root}" \
  DOTFILES_DOTMAN_MANAGER_REPO_NAME="${dotman_manager_repo_name}" \
    uv run --no-project --with tomlkit python - "$1" <<'PY'
from pathlib import Path
import os
import sys

import tomlkit


repo_name = os.environ["DOTFILES_DOTMAN_MANAGER_REPO_NAME"]
repo_root = os.environ["DOTFILES_DOTMAN_REPO_ROOT"]
overlay_path = Path(sys.argv[1])

repo_config = tomlkit.table()
repo_config.add("path", repo_root)
repo_config.add("order", 10)
repo_config.add("state_key", repo_name)

repos_config = tomlkit.table()
repos_config.add(repo_name, repo_config)

doc = tomlkit.document()
doc.add("repos", repos_config)

overlay_path.write_text(doc.as_string(), encoding="utf-8")
PY
}

install_dotman_manager_config() {
  dotman_manager_config_path="$(dotman_config_path)"
  dotman_config_overlay_path="$(mktemp "${TMPDIR:-/tmp}/dotman-config-overlay.XXXXXX.toml")"

  log "installing dotman manager config at ${dotman_manager_config_path}"
  mkdir -p "$(dirname -- "${dotman_manager_config_path}")"
  generate_dotman_config_overlay "${dotman_config_overlay_path}"

  # Use the repo TOML transform so init preserves unrelated manager config while
  # replacing only this repo registration. Do not hand-roll TOML merge in shell.
  (
    cd -- "${repo_root}"
    uv run --no-project --with tomlkit python scripts/toml_transform.py \
      "${dotman_manager_config_path}" \
      "${dotman_manager_config_path}" \
      --mode merge \
      --overlay-file "${dotman_config_overlay_path}" \
      --selector-type remove \
      --selectors "repos.${dotman_manager_repo_name}" \
      --compare-file "${dotman_manager_config_path}"
  )
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    log "uv already installed at $(command -v uv)"
    return 0
  fi

  if command -v brew >/dev/null 2>&1; then
    log "installing uv with brew"
    if brew install uv; then
      return 0
    fi
  elif command -v scoop >/dev/null 2>&1; then
    log "installing uv with scoop"
    if scoop install uv; then
      return 0
    fi
  elif command -v pacman >/dev/null 2>&1; then
    log "installing uv with pacman"
    if sudo pacman -Sy --needed uv; then
      return 0
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    log "installing uv with apt-get"
    if sudo apt-get update && sudo apt-get install -y uv; then
      return 0
    fi
  elif command -v dnf >/dev/null 2>&1; then
    log "installing uv with dnf"
    if sudo dnf install -y uv; then
      return 0
    fi
  elif command -v zypper >/dev/null 2>&1; then
    log "installing uv with zypper"
    if sudo zypper --non-interactive install uv; then
      return 0
    fi
  elif command -v apk >/dev/null 2>&1; then
    log "installing uv with apk"
    if sudo apk add uv; then
      return 0
    fi
  fi

  if ! command -v curl >/dev/null 2>&1; then
    die "curl is required for the fallback uv installer"
  fi

  log "installing uv with the official installer into ${default_uv_bin_dir}"
  mkdir -p "${default_uv_bin_dir}"
  run_installer_script
}

install_dotman() {
  log "installing dotman with uv tool install --upgrade ${dotman_tool_spec}"
  uv tool install --upgrade "${dotman_tool_spec}"
}

install_uv
prepend_path "${default_uv_bin_dir}"

export PATH

install_dotman_manager_config
install_dotman

log "bootstrap complete"

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
repo_core_env_path="${repo_root}/packages/shell/files/env.core.sh"
default_uv_bin_dir="${HOME}/.local/bin"
dotman_tool_spec_default='git+https://github.com/ewgdg/dotman.git'
dotman_tool_spec="${DOTMAN_TOOL_SPEC:-$dotman_tool_spec_default}"

if [ -r "${repo_core_env_path}" ]; then
  # Keep bootstrap-time PATH/XDG behavior aligned with the managed shell profile.
  # shellcheck source=/dev/null
  . "${repo_core_env_path}"
fi

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
  installer_script_path="$(mktemp "${TMPDIR:-/tmp}/uv-install.XXXXXX.sh")"
  trap 'rm -f "${installer_script_path}"' EXIT

  curl --proto '=https' -LsSf https://astral.sh/uv/install.sh -o "${installer_script_path}"
  env UV_UNMANAGED_INSTALL="${default_uv_bin_dir}" UV_NO_MODIFY_PATH=1 sh "${installer_script_path}"
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

install_dotman

log "bootstrap complete"

#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '%s\n' "$*" >&2
}

die() {
  log "$*"
  exit 1
}

script_dir="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
  pwd -P
)"
repo_root="${script_dir}"

if [[ -r "${HOME}/.profile" ]]; then
  # Reuse the current login-shell defaults instead of writing new persistent env.
  # shellcheck source=/dev/null
  . "${HOME}/.profile"
fi

dotdrop_config_path="${repo_root}/config.yaml"

if [[ ! -f "${dotdrop_config_path}" ]]; then
  die "dotdrop config not found at ${dotdrop_config_path}"
fi

default_uv_bin_dir="${HOME}/.local/bin"
dotdrop_sudo_script="${repo_root}/dotfiles/bin/dotdrop-sudo"
export DOTDROP_CONFIG="${dotdrop_config_path}"

prepend_path() {
  case ":${PATH:-}:" in
    *":$1:"*) ;;
    *)
      if [[ -n "${PATH:-}" ]]; then
        PATH="$1:${PATH}"
      else
        PATH="$1"
      fi
      ;;
  esac
}

normalize_dir() {
  if [[ -d "$1" ]]; then
    (
      cd -- "$1" >/dev/null 2>&1
      pwd -P
    )
  else
    printf '%s\n' "$1"
  fi
}

run_installer_script() {
  local installer_script_path

  installer_script_path="$(mktemp "${TMPDIR:-/tmp}/uv-install.XXXXXX.sh")"
  trap 'rm -f "${installer_script_path}"' EXIT

  curl --proto '=https' -LsSf https://astral.sh/uv/install.sh -o "${installer_script_path}"
  env UV_UNMANAGED_INSTALL="${default_uv_bin_dir}" sh "${installer_script_path}"
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

install_dotdrop() {
  log "installing dotdrop with uv tool"
  uv tool install dotdrop
}

run_dotdrop_apply() {
  if [[ ! -x "${dotdrop_sudo_script}" ]]; then
    die "dotdrop-sudo wrapper not found at ${dotdrop_sudo_script}"
  fi

  log "running dotdrop-sudo install"
  "${dotdrop_sudo_script}" install "$@"
}

should_run_dotdrop_install=true
dotdrop_install_args=()

while (( $# > 0 )); do
  case "$1" in
    --no-install)
      should_run_dotdrop_install=false
      shift
      ;;
    *)
      dotdrop_install_args+=("$1")
      shift
      ;;
  esac
done

install_uv
prepend_path "${default_uv_bin_dir}"

if command -v uv >/dev/null 2>&1; then
  uv_tool_bin_dir="$(uv tool dir --bin)"
  uv_tool_bin_dir="$(normalize_dir "${uv_tool_bin_dir}")"
  prepend_path "${uv_tool_bin_dir}"
fi

export PATH

install_dotdrop

if [[ "${should_run_dotdrop_install}" == true ]]; then
  run_dotdrop_apply "${dotdrop_install_args[@]}"
fi

log "bootstrap complete"

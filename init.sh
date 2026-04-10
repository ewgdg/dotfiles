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
dotman_repo_name="${DOTMAN_REPO_NAME:-main}"
dotman_tool_spec_default='git+https://github.com/ewgdg/dotman.git'
dotman_tool_spec="${DOTMAN_TOOL_SPEC:-$dotman_tool_spec_default}"

if [ -r "${repo_core_env_path}" ]; then
  # Keep bootstrap-time PATH/XDG behavior aligned with the managed shell profile.
  # shellcheck source=/dev/null
  . "${repo_core_env_path}"
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

normalize_dir() {
  if [ -d "$1" ]; then
    (
      cd -- "$1" >/dev/null 2>&1
      pwd -P
    )
  else
    printf '%s\n' "$1"
  fi
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

write_dotman_config() {
  dotman_config_path="$(mktemp "${TMPDIR:-/tmp}/dotman-config.XXXXXX.toml")"
  cat >"${dotman_config_path}" <<EOF
[repos.${dotman_repo_name}]
path = "${repo_root}"
order = 10
EOF
  printf '%s\n' "${dotman_config_path}"
}

run_dotman_apply() {
  binding="$1"
  shift

  if ! command -v dotman >/dev/null 2>&1; then
    die "dotman not found in PATH after installation"
  fi

  dotman_config_path="$(write_dotman_config)"
  trap 'rm -f "${dotman_config_path}"' EXIT HUP INT TERM

  log "tracking ${binding}"
  dotman --config "${dotman_config_path}" track "${binding}"

  log "running dotman push"
  dotman --config "${dotman_config_path}" push "$@"
}

should_run_dotman_push=true
binding=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-install)
      should_run_dotman_push=false
      shift
      ;;
    -p|--profile)
      [ "$#" -ge 2 ] || die "$1 requires a value"
      binding="${dotman_repo_name}:$2@$2"
      shift 2
      ;;
    -b|--binding)
      [ "$#" -ge 2 ] || die "$1 requires a value"
      binding="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      break
      ;;
    *)
      if [ -z "${binding}" ]; then
        binding="$1"
        shift
      else
        break
      fi
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

install_dotman

if [ "${should_run_dotman_push}" = true ]; then
  if [ -z "${binding}" ]; then
    die "missing binding: pass a full binding like host/linux@host/linux or use -p host/linux"
  fi
  run_dotman_apply "${binding}" "$@"
fi

log "bootstrap complete"

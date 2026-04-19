path_prepend() {
  # Prepend a directory to PATH if it exists and is not already present.
  if [ -d "$1" ]; then
    case ":${PATH:-}:" in
      *":$1:"*) ;;
      *)
        if [ -n "${PATH:-}" ]; then
          PATH="$1:$PATH"
        else
          PATH="$1"
        fi
        ;;
    esac
  fi
}

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
# Sentinel for push guards and ad-hoc checks. Full file name is included to
# keep collision risk low with arbitrary user/session variables.
export DOTFILES_ENV_CORE_SH_LOADED='dotfiles:packages/shell/files/env.core.sh'
export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"

path_prepend "$BUN_INSTALL/bin"
path_prepend "$HOME/.npm/bin"
path_prepend "$HOME/.cargo/bin"
path_prepend "$HOME/.local/bin"
path_prepend "$HOME/bin"

export PATH

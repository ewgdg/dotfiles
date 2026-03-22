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

if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
export BUN_INSTALL_BIN="$HOME/.local/bin"
export BUN_INSTALL_GLOBAL_DIR="$XDG_DATA_HOME/bun/install/global"
export BUN_INSTALL_CACHE_DIR="$XDG_CACHE_HOME/bun/install/cache"

path_prepend "$XDG_DATA_HOME/npm/bin"
path_prepend "$XDG_DATA_HOME/pnpm/bin"
path_prepend "$HOME/.cargo/bin"
path_prepend "$HOME/.local/bin"
path_prepend "$HOME/bin"

export PATH

path_prepend() {
  # Keep future install locations available without duplicating PATH entries.
  if [ -n "${1:-}" ]; then
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

path_append() {
  # Append a directory to PATH if it exists and is not already present.
  if [ -d "$1" ]; then
    case ":${PATH:-}:" in
      *":$1:"*) ;;
      *)
        if [ -n "${PATH:-}" ]; then
          PATH="$PATH:$1"
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
export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
export PNPM_HOME="${PNPM_HOME:-$XDG_DATA_HOME/pnpm}"
export GOPATH="${GOPATH:-$HOME/go}"

path_prepend "${GOPATH%%:*}/bin"

path_prepend "$BUN_INSTALL/bin"
path_prepend "$HOME/.npm/bin"
path_prepend "$HOME/.cargo/bin"
path_prepend "$HOME/.local/bin"
path_prepend "$HOME/bin"
path_prepend "$PNPM_HOME/bin"

export PATH

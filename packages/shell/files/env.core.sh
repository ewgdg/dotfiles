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
export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"

go_path="${GOPATH:-}"
if [ -z "$go_path" ] && command -v go >/dev/null 2>&1; then
  go_path="$(go env GOPATH 2>/dev/null)"
fi
if [ -n "$go_path" ]; then
  path_prepend "$go_path/bin"
fi
unset go_path

path_prepend "$BUN_INSTALL/bin"
path_prepend "$HOME/.npm/bin"
path_prepend "$HOME/.cargo/bin"
path_prepend "$HOME/.local/bin"
path_prepend "$HOME/bin"

export PATH

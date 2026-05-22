# Install Marker Packages

Some packages exist only to ensure software is installed and do not manage any user-facing config files.
For those cases, keep a small tracked marker file so the package still has managed state.

## Convention

Use marker files under this repo-owned XDG state namespace:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/installed/
```

Use `dotfiles`, not `dotman`: these markers belong to this repository, not to dotman internals.
Marker content should list installed packages/tools, one per line.
Mirror the package namespace when useful.

Examples:

- `rustup` -> `~/.local/state/dotfiles/installed/rustup`
- `linux/lutris` -> `~/.local/state/dotfiles/installed/linux/lutris`
- namespaced packages should usually keep their namespace, e.g. `mac/fonts` -> `~/.local/state/dotfiles/installed/mac/fonts`

## Package Pattern

Example install-only package:

```toml
id = "rustup"
description = "Rust toolchain bootstrap marker and install hooks"

[targets.f_local_state_dotfiles_installed_rustup]
source = "files/local/state/dotfiles/installed/rustup"
path = "~/.local/state/dotfiles/installed/rustup"

# Marker exists so install-only packages still have a managed target.
[hooks]
pre_push = [
  'sh "$DOTMAN_REPO_ROOT/scripts/install_rustup.sh"',
]
```

## When To Use

Use this pattern when:

- package has install hooks but no config files yet
- package should remain explicit in group membership and dependency graphs
- you want a stable place to hang future package-local state

Do not use this pattern when the package already manages real config files or directories.

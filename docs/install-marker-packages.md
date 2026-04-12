# Install Marker Packages

Some packages exist only to ensure software is installed and do not manage any user-facing config files.
For those cases, keep a small tracked marker file so the package still has managed state.

## Convention

Use marker files under:

```text
~/.local/state/dotman/installed/
```

Mirror the package namespace when useful.

Examples:

- `rustup` -> `~/.local/state/dotman/installed/rustup`
- `linux/lutris` -> `~/.local/state/dotman/installed/lutris`
- if name collisions become possible, use nested paths such as `~/.local/state/dotman/installed/linux/lutris`

## Package Pattern

Example install-only package:

```toml
id = "rustup"
description = "Rust toolchain bootstrap marker and install hooks"

[targets.f_local_state_dotman_installed_rustup]
source = "files/local/state/dotman/installed/rustup"
path = "~/.local/state/dotman/installed/rustup"

# Marker exists so install-only packages still have tracked state in dotman.
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

# Install Marker Packages

Install marker files are a legacy fallback for install-only packages.
Prefer probe targets for new conditional install/update work; see `docs/install-probe-targets.md`.

Use a marker only when a package still needs a real managed file target and a probe target cannot model the requirement.

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

## Legacy Package Pattern

```toml
id = "example-toolchain"
description = "Example install marker"

[targets.f_local_state_dotfiles_installed_example_toolchain]
source = "files/local/state/dotfiles/installed/example-toolchain"
path = "~/.local/state/dotfiles/installed/example-toolchain"
```

## When To Use

Use this pattern only when:

- package needs a stable tracked file target for compatibility or state ownership
- a probe target cannot express the live requirement

Do not use this pattern just to keep an install-only package selectable. Use an install probe target instead.

# Dotfiles

This repo manages user and system configuration with the new [`dotman`](https://github.com/ewgdg/dotman) repo layout.

## Repo Layout

Active repo content lives under:

- `packages/` — package definitions and tracked source files under `packages/<id>/files/...`
- `groups/` — reusable selector composition
- `profiles/` — variable-only profile definitions
- `scripts/` — shared helper scripts used by package hooks and target commands
- `repo.toml` — repo-wide defaults such as ignore rules
- `local.toml` — machine-local overrides that should not be committed

## First Bootstrap

Use `init.sh` on a new machine:

```sh
./init.sh -p host/linux
# or
./init.sh main:host/linux@host/linux
```

What `init.sh` does:

- installs `uv` if needed
- installs `dotman` with `uv tool install`
- sources `packages/shell/files/env.core.sh`
- creates a temporary single-repo dotman manager config for this checkout
- runs `dotman track` and `dotman push` by default

By default `init.sh` installs dotman from:

```sh
git+https://github.com/ewgdg/dotman.git
```

Override it with `DOTMAN_TOOL_SPEC` only if you need a different source:

```sh
DOTMAN_TOOL_SPEC='git+https://github.com/ewgdg/dotman.git' ./init.sh -p host/linux
```

Bootstrap only, without tracking or pushing:

```sh
./init.sh --no-install
```

## Normal Workflow

After bootstrap, use dotman as the primary interface.

Typical flow:

1. Register this repo in your dotman manager config.
2. Track the binding you want.
3. Use `dotman push` for repo-to-live changes.
4. Use `dotman pull` for live-to-repo changes.

Example commands below assume the repo is registered as `main` in your dotman
config:

```sh
dotman track main:host/linux@host/linux
dotman push
dotman pull

dotman list tracked
dotman info tracked git
```

For narrower work, you can track or inspect smaller selectors directly:

```sh
dotman track main:git@host/linux
dotman push git
dotman pull git
```

## Choosing Bindings

Common host entrypoints:

- `main:host/linux@host/linux`
- `main:host/mac@host/mac`

Examples of smaller selectors:

- `main:git@host/linux`
- `main:nvim@host/linux`
- `main:shell@host/linux`

Groups choose what to manage.
Profiles provide the variable context used to resolve those selections.

## Local Overrides

Use `local.toml` for machine-local values that should not be committed.

Example:

```toml
[vars]
hostname = "workstation"
```

## Notes

- Shared shell bootstrap behavior now comes from
  `packages/shell/files/env.core.sh`.
- Transform helpers in `scripts/` are still part of the active repo and are used
  by package target commands.
- Repo Python helpers are expected to run through `uv run ...` (or
  `uv run --project "$DOTMAN_REPO_ROOT" ...` inside dotman hooks). Do not rely
  on direct `python path/to/script.py` execution.

## Related Docs

- `docs/bootstrap.md`
- `docs/transform-cli-interface.md`
- `docs/transform-engine-interface.md`

# Dotfiles

This repo manages user and system configuration with the [`dotman`](https://github.com/ewgdg/dotman) repo layout.

## Repo Layout

Active repo content lives under:

- `packages/` — package definitions and tracked source files under `packages/<id>/files/...`
- `groups/` — reusable selector composition
- `profiles/` — variable-only profile definitions
- `scripts/` — shared helper scripts used by package hooks and target commands
- `repo.toml` — repo-wide defaults such as ignore rules

## First Bootstrap

Use `init.sh` to install bootstrap dependencies:

```sh
./init.sh
```

`./activate.sh` is recommended before `./init.sh` and before first
`dotman push`.

`activate.sh` loads repo core env (`packages/shell/files/env.core.sh`) into the current shell, including XDG dirs, and PATH entries such as `~/.local/bin`.
This is to align current shell with the repo's profile env (XDG paths, PATH). Skip if already running a login shell started after the profile was pushed.

```sh
. ./activate.sh
./init.sh
```

What `init.sh` does:

- installs `uv` if needed
- installs `dotman` with `uv tool install`

By default `init.sh` installs dotman from:

```sh
git+https://github.com/ewgdg/dotman.git
```

Override it with `DOTMAN_TOOL_SPEC` only if you need a different source:

```sh
DOTMAN_TOOL_SPEC='git+https://github.com/ewgdg/dotman.git' ./init.sh
```

## Normal Workflow

After bootstrap, use dotman as the primary interface.

If `shell` package is pushed and you start a new login shell, the managed
profile loads the same core env automatically, so manual `./activate.sh` is no
longer needed.

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

## Notes

- Helpers in `scripts/` are still part of the active repo and are used
  by package target commands.
- Repo Python helpers are expected to run through `uv run ...` (or
  `uv run --project "$DOTMAN_REPO_ROOT" ...` inside dotman hooks). Do not rely
  on direct `python path/to/script.py` execution.

## Related Docs

check `docs/` directory.

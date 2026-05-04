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

Source `./activate.sh` before `./init.sh` and before first `dotman push`; do not run it directly.

`activate.sh` loads repo core env (`packages/shell/files/env.core.sh`) into the current shell, including XDG dirs and PATH entries such as `~/.local/bin`, then exports a hash token for stale-shell detection.
This is to align current shell with the repo's profile env. Skip if already running a login shell started after the shell package was pushed.
`dotman push` is guarded by that shell env token. If current shell does not carry current repo core env token yet, the guard stops with a fix message instead of prompting.

```sh
. ./activate.sh
./init.sh
```

What `init.sh` does:

- installs `uv` if needed
- registers this checkout in `$XDG_CONFIG_HOME/dotman/config.toml` (or
  `~/.config/dotman/config.toml`) as `repos.main`, preserving unrelated TOML
  config with the repo TOML transform helper
- installs `dotman` with `uv tool install`

By default `init.sh` installs dotman from:

```sh
git+https://github.com/ewgdg/dotman.git
```

Override it with `DOTMAN_TOOL_SPEC` only if you need a different source:

```sh
DOTMAN_TOOL_SPEC='git+https://github.com/ewgdg/dotman.git' ./init.sh
```

The manager repo entry defaults to name `main`, order `10`, and `state_key = "main"`.
Override only for unusual multi-repo bootstraps:

```sh
DOTFILES_DOTMAN_MANAGER_REPO_NAME=work ./init.sh
```

## Normal Workflow

After bootstrap, use dotman as the primary interface.

If the `shell` package is pushed and you start a new login shell, the managed
profile sources the deployed `~/.config/shell/env.core.sh` automatically, so manual
`./activate.sh` is no longer needed.

Typical flow:

1. Run `./init.sh` to register this repo in your dotman manager config.
2. Track the binding you want.
3. Use `dotman push` for repo-to-live changes.
4. Use `dotman pull` for live-to-repo changes.

Example commands below assume the repo is registered as `main` in your dotman
config:

```sh
dotman track main:host/linux-niri@host/linux-niri
dotman push
dotman pull

dotman list tracked
dotman info tracked git
```

For narrower work, you can track or inspect smaller selectors directly:

```sh
dotman track main:git@host/linux-niri
dotman push git
dotman pull git
```

## Choosing Bindings

Common host entrypoints:

- `main:host/linux-niri@host/linux-niri`
- `main:host/mac@host/mac`

Examples of smaller selectors:

- `main:git@host/linux-niri`
- `main:nvim@host/linux-niri`
- `main:shell@host/linux-niri`

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

# Bootstrap

Use `init.sh` to bootstrap `uv`, install [`dotman`](https://github.com/ewgdg/dotman), and do an initial track +
push for this repo.

## Basic Usage

```sh
./init.sh -p host/linux
# or
./init.sh main:host/linux@host/linux
```

Bootstrap only, without tracking or pushing:

```sh
./init.sh --no-install
```

## What `init.sh` Does

- installs `uv` if needed
- uses `UV_NO_MODIFY_PATH=1` for the fallback `uv` installer
- sources `packages/shell/files/env.core.sh`
- installs `dotman` via `uv tool install --upgrade`
- creates a temporary single-repo dotman manager config that points at this checkout
- runs `dotman track <binding>`
- runs `dotman push`

The script manages `PATH` itself inside the bootstrap process, so it does not
rely on the `uv` installer mutating shell rc files.

## Dotman Tool Source

By default `init.sh` installs dotman from:

```text
git+https://github.com/ewgdg/dotman.git
```

Override it with `DOTMAN_TOOL_SPEC` only if you need a different source:

```sh
DOTMAN_TOOL_SPEC='git+https://github.com/ewgdg/dotman.git' ./init.sh -p host/linux
```

## After Bootstrap

For ongoing use, put this repo in your normal dotman manager config instead of
relying on `init.sh`'s temporary config.

Example manager config:

```toml
[repos.main]
path = "~/projects/dotfiles"
order = 10
```

Then use dotman normally:

```sh
dotman track main:host/linux@host/linux
dotman push
dotman pull
```

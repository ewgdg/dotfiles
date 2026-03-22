# Dotdrop Bootstrap

Use `init.sh` to bootstrap `uv`, install `dotdrop` as a `uv` tool, and export
the shell variables needed to use this repo immediately. By default it also
runs the repo's `dotmanage install`.

Usage:

```sh
./init.sh
```

Behavior:

- If `uv` is already installed, the script reuses it.
- If `uv` is missing, the script first tries a local system package manager
  such as `brew`, `scoop`, `pacman`, `apt-get`, `dnf`, `zypper`, or `apk`.
- If no supported package manager install succeeds, it falls back to the
  official `uv` installer with `UV_UNMANAGED_INSTALL=~/.local/bin`.
- The script sources `dotfiles/profile.bootstrap.sh` before bootstrapping so
  install-time tools use the same XDG and PATH defaults that the managed shell
  profile expects.
- The installer target is `~/.local/bin`.
- `DOTDROP_CONFIG` always points to the `config.yaml` in the same repo as
  `init.sh`.
- `PATH` is updated inside the script process before later bootstrap steps run.
- `dotdrop` is then installed with `uv tool install dotdrop`.
- After bootstrapping, the script runs the repo-local `dotfiles/bin/dotmanage install`
  by default so mixed user and system targets are handled correctly.

Bootstrap only:

```sh
./init.sh --no-install
```

Pass any other arguments through to `dotmanage install`, for example:

```sh
./init.sh -p xian-linux-server
```

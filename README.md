# Dotfiles

This repo manages user and system configuration with `dotdrop`.

- Managed sources live under `dotfiles/`.
- Source-to-destination mappings, profiles, actions, and transforms live in `config.yaml`.
- Use `dotmanage` when a target set includes privileged paths such as `/etc`.
- Use plain `dotdrop` when you are only working with user-owned files under `~`.

## First Install

Use `init.sh` on a new machine:

```sh
./init.sh -p <profile>
```

`init.sh` will:

- install `uv` if needed
- install `dotdrop` as a `uv` tool
- source the shared repo bootstrap environment from `dotfiles/profile.bootstrap.sh`
- use this repo's `config.yaml`
- run `dotmanage install` by default

Bootstrap only, without applying files:

```sh
./init.sh --no-install
```

## Main Commands

For system + user files, use the wrapper in `dotfiles/bin/dotmanage`:

```sh
dotmanage install -p <profile>
dotmanage update -p <profile>
```

Use this when the selected profile or keys include both home-directory files and
privileged destinations.

Before `dotmanage` invokes `dotdrop`, it sources
`dotfiles/profile.bootstrap.sh` so install-time tools see the same XDG and PATH
defaults as the managed shell profile.

For templated file sources, `dotmanage update` automatically uses the repo's
template-aware merge helper instead of plain `dotdrop update`.

For user-only files, use plain `dotdrop` directly:

```sh
dotdrop compare -p <profile>
dotdrop install -p <profile> -k d_config_nvim
dotdrop update -p <profile> -k d_config_nvim
```

That pattern is appropriate for keys that only write under your home directory,
for example `~/.config/...`, `~/bin`, or `~/.ssh/...`.

## Finding Keys

If you do not remember the key name, list the keys for a profile and filter the
output:

```sh
dotdrop files -p <profile> --grepable | rg nvim
```

That is usually the fastest way to find a key by app name, destination path, or
source path. Once you have a match, inspect it in more detail with:

```sh
dotdrop detail -p <profile> <key>
```

## Profiles

Profiles are defined in `config.yaml`. Choose the machine-specific profile you
want to install and pass it as `<profile>` in the commands above.

There are also shared building-block profiles such as `base`, `posix_base`,
`os_arch`, `os_mac`, `de_kde`, and `de_niri`.

When adding new dotfiles, make sure the entry is included by the profile you
actually install, otherwise `dotdrop install` will never deploy it.

## Workflow

Typical flow:

1. Run `./init.sh -p <profile>` on first setup.
2. Use `dotmanage install -p <profile>` for full applies that include system files.
3. Use `dotdrop` directly for user-only keys during focused iteration.
4. Use `dotmanage update -p <profile>` to sync live changes back into the repo when privileged files are involved.

## Related Docs

- `docs/dotdrop-bootstrap.md`
- `docs/dotdrop-template-update.md`
- `docs/dotdrop-vs-chezmoi-vs-ansible.md`
- `docs/user-systemd-service-actions.md`

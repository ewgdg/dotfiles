# Repository Guidelines

## Project Structure & Module Organization

This repository manages user and system configuration with `dotdrop`. The main mapping lives in `config.yaml`; Managed files are stored under `dotfiles/`, mirroring destination paths such as `dotfiles/config/nvim`, `dotfiles/bin`, and `dotfiles/etc`. Helper scripts live in `scripts/`. Use `docs/` for contributor-facing notes about workflows or non-obvious behavior.

## Develop Guidelines

When add a new config file to dotdrop, also add an appropriate post/pre action for it if necessary, for example, installing the corresponding app for the config.
When add a new dotdrop entry in `config.yaml`, also verify it is included by the relevant profile. A dotfile entry that is not referenced by the active profile will not be deployed by `dotdrop install`.
The action need to be idempotent.
If a dotdrop action is only used in one place, prefer inlining the command at that call site instead of creating a single-use named action.
Dotdrop transform scripts must write the output path passed by dotdrop and preserve the source file mode on that output.
Performance is a concern for long running services.

## Build, Test, and Development Commands

There is no application build step. The core workflow is syncing and validating managed files.

`dotdrop compare` previews drift between the repo and live targets. `dotdrop-sudo update` imports local changes, including root-owned paths. `dotdrop-sudo install` applies a profile to the machine.

## Security & Configuration Tips

Do not commit credentials, generated state, or local-only overrides that are already excluded by `cmpignore`/`upignore`.

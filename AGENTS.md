# Repository Guidelines

## Project Structure & Module Organization

This repository manages user and system configuration with `dotdrop`. The main mapping lives in `config.yaml`; Managed files are stored under `dotfiles/`, mirroring destination paths such as `dotfiles/config/nvim`, `dotfiles/bin`, and `dotfiles/etc`. Helper scripts live in `scripts/`. Use `docs/` for contributor-facing notes about workflows or non-obvious behavior.

## Build, Test, and Development Commands

There is no application build step. The core workflow is syncing and validating managed files.

`dotdrop compare` previews drift between the repo and live targets. `dotdrop-sudo update` imports local changes, including root-owned paths. `dotdrop-sudo install` applies a profile to the machine.

## Deploy Guidelines

When ask to deploy the changes, do not use `dotdrop install` if possible as that requires sudo for actions involves installing.
Just simply copy the target files to the destinations.

## Security & Configuration Tips

Do not commit credentials, generated state, or local-only overrides that are already excluded by `cmpignore`/`upignore`.

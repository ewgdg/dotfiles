# Repository Guidelines

## Project Structure & Module Organization

This repository manages user and system configuration with `dotdrop`. The main mapping lives in `config.yaml`; managed files are stored under `dotfiles/`, mirroring destination paths such as `dotfiles/config/nvim`, `dotfiles/bin`, and `dotfiles/etc`. Shared cross-package helper scripts live in `scripts/`. Package-specific helpers should live under that package, for example `packages/<id>/scripts/`, and be referenced via `DOTMAN_PACKAGE_ROOT` so package stays self-contained. Use `docs/` for contributor-facing notes about workflows or non-obvious behavior.

## Develop Guidelines

When add a new config file to dotdrop, also add an appropriate post/pre action for it if necessary, for example, installing the corresponding app for the config.
When add a new dotdrop entry in `config.yaml`, also verify it is included by the relevant profile. A dotfile entry that is not referenced by the active profile will not be deployed by `dotdrop`.
The action need to be idempotent.
Use `install-if 'pkg' 'predicate'` to conditionally install a package (e.g. `- install-if 'foo' 'command -v foo'`). Arg order is package first, predicate second.
Dotdrop action arguments use `{0}`, `{1}`, etc. as positional placeholders — dotdrop does NOT auto-append extra tokens. When calling an action with multiple packages, always quote them as a single argument: `- install 'pkg1 pkg2'`. Unquoted extra tokens (e.g. `- install pkg1 pkg2`) are silently dropped.
If a dotdrop action is only used in one place, prefer inlining the command at that call site instead of creating a single-use named action.
Dotdrop transform scripts must write the output path passed by dotdrop and preserve the source file mode on that output.
Performance is a concern for long running services.
Do not edit files with a `.archived` suffix unless the user explicitly asks.

## Build, Test, and Development Commands

There is no application build step. The core workflow is syncing and validating managed files.

Use `uv run dotdrop` for agent workflows in this repo. `dotdrop compare` previews drift between the repo and live targets, and `dotdrop install` applies selected profiles or keys. If you need the user-facing wrapper for a specific manual workflow, refer to `README.md`, but keep agent instructions centered on `dotdrop`.

## Security & Configuration Tips

Do not commit credentials, generated state, or local-only overrides that are already excluded by `cmpignore`/`upignore`.

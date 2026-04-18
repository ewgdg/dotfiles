# Repository Guidelines

## Project Structure & Module Organization

This repository manages user and system configuration with `dotman`. Managed files are stored under `packages/<id>/files/...`, mirroring destination paths. Shared cross-package helper scripts live in `scripts/`. Package-specific helpers should live under that package, for example `packages/<id>/scripts/`, and be referenced via `DOTMAN_PACKAGE_ROOT` so the package stays self-contained. Use `docs/` for contributor-facing notes about workflows or non-obvious behavior.

## Develop Guidelines

When adding a new config file, also add an appropriate post/pre action for it if necessary, for example, installing the corresponding app for the config.
Actions must be idempotent.
Use `install-if 'pkg' 'predicate'` to conditionally install a package (e.g. `- install-if 'foo' 'command -v foo'`). Arg order is package first, predicate second.
Action arguments use `{0}`, `{1}`, etc. as positional placeholders. When calling an action with multiple packages, always quote them as a single argument: `- install 'pkg1 pkg2'`. Unquoted extra tokens are silently dropped.
If an action is only used in one place, prefer inlining the command at that call site instead of creating a single-use named action.
Transform scripts must write the output path passed by dotman and preserve the source file mode on that output.
Performance is a concern for long running services.
Do not edit files with a `.archived` suffix unless the user explicitly asks.

## Build, Test, and Development Commands

There is no application build step. The core workflow is syncing and validating managed files.

Use `dotman` for agent workflows in this repo. `dotman pull` previews or applies drift between the repo and live targets, and `dotman push` syncs live files back into the repo. If you need the user-facing workflow details, refer to `README.md`.

## Security & Configuration Tips

Do not commit credentials, generated state, or local-only overrides that are already excluded by `cmpignore`/`upignore`.

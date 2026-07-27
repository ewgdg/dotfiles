# Single upgrade command

## Goal

Ship a cross-platform `upgrade` command backed by Topgrade, with an explicit
`upgrade services` dispatch to the existing services repository updater.

## Intention

Provide one attended entry point for workstation package and tool maintenance
without duplicating each ecosystem's updater. Keep Docker deployment explicit,
preserve package-manager ownership of executables, and make all routing behavior
observable in tests.

## Scope & Constraints

- Add a dedicated `topgrade` dotman package selected by both Arch and macOS.
- Manage Topgrade's configuration and `~/.local/bin/upgrade` in that package.
- Delegate every non-service invocation to Topgrade with exact argument
  forwarding.
- Delegate the exact `upgrade services` invocation to
  `$(xdg-user-dir PROJECTS)/services/services.sh update`.
- Add `gup` as an idempotently probed prerequisite of `go-lang`.
- Preserve unrelated worktree changes and do not run any real upgrades during
  validation.
- Follow the decisions in `packages/topgrade/README.md`.

## Work Plan

1. Add behavior tests for launcher delegation, argument forwarding, explicit
   service dispatch, and missing-service diagnostics.
2. Add the `topgrade` package, managed configuration, launcher, install probe,
   and cross-platform group membership.
3. Add the `gup` install probe and hook to `go-lang`.
4. Run focused tests, repository tests, manifest/config checks, and whitespace
   validation.

## Validation

- `env -u NO_COLOR uv run pytest -q tests/test_upgrade_command.py`
- `env -u NO_COLOR uv run pytest -q`
- `git diff --check`
- Dotman inspection/plan commands that do not push or pull live state.

## Progress

- [x] Design grilled and confirmed.
- [x] Launcher tests added and observed failing before implementation.
- [x] Package, launcher, configuration, and `gup` prerequisite implemented.
- [x] Focused and full validation passed.

## Decisions

- Topgrade is the package/tool orchestrator; `paru` is the Arch owner.
- Upgrades remain attended with native retry/continue/quit handling.
- Only the dotfiles checkout is allowlisted for fast-forward Git pulls.
- Docker deployment remains the explicit `upgrade services` operation and
  reuses the services repository's tested updater.
- Fork synchronization and periodic checking are out of scope.

## Outcomes & Retrospective

- The `topgrade` package is selected through `unix/utils` on both supported host
  profiles and owns installation, policy, and launcher targets.
- The launcher preserves Topgrade and service-updater arguments and exit status,
  while service lookup failures are actionable.
- `go-lang` installs `gup` only when its command is absent.
- Validation completed with 11 focused launcher/policy tests and 169 total
  repository tests. Shell syntax, dotman catalog resolution, and `git diff
  --check` also passed.

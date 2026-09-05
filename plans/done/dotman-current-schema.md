# Update dotman definitions to current upstream

## Goal and constraints

Keep all managed packages and host profiles usable with current dotman main.
Change repository definitions, tests, and documentation only; do not run live
push/pull, install software, or rewrite manager state.

## Work plan

1. Compare installed dotman and upstream contracts; inventory local definitions.
2. Update ignores and named path rules without retaining obsolete schema.
3. Validate every package/group/profile using current upstream and run affected
   bootstrap and transform tests against that same revision.
4. Document supported definitions and any operational consequences.

## Validation

Use an isolated upstream checkout and temporary manager config/state. Catalog
validation must not execute install probes or hooks. Test failures should precede
schema changes, then pass with the migrated definitions.

## Progress

- Upstream inspection found hard-cut ignore and path-rule schema changes.
- Local inventory: 66 packages, 27 groups, 18 profiles; bootstrap already uses
  supported manager state keys and public transform CLI.
- Updated repo config and 12 package manifests; all 66 packages, 27 groups, and
  18 profiles load and resolve against upstream `be6cb33`.
- Updated test lookups for named rules and symmetric ignores; removed numeric
  array traversal from the affected tests.
- Added a catalog integration test. All 41 focused catalog/bootstrap/transform/
  instruction-loading tests pass against the exact upstream checkout (7.12s).

## Decisions

- Preserve existing ignore exclusions as a symmetric union; new upstream has no
  directional ignore lists. This also excludes `.dotdropbak`, Noctalia config
  JSON/plugins, and SDDM's local autologin override during push. No currently
  tracked source files match these newly symmetric exclusions.
- Keep the existing bootstrap source policy; pinning upgrades is outside scope.

## Outcome

Current schema is adopted without compatibility aliases. No live push/pull,
software installation, or manager-state modification was performed. Profiles
and bootstrap needed no schema changes. Migration findings are recorded in the
journal rather than maintained as a separate compatibility document.

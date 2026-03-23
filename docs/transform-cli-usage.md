# Transform CLI Usage

This document is about how to use the shared transform CLI for repo round-trip
workflows.

For the generic CLI contract, see
[`docs/transform-cli-interface.md`](/Users/xian/Projects/dotfiles/docs/transform-cli-interface.md).
For format-specific matcher syntax and merge direction, see the individual
format docs.

## Goal

The main round-trip use case is:

- install from repo to live file
- update from live file back into repo
- keep local noise out of the repo when possible

In this repo, that usually maps to:

- `trans_update`: normalize the live file before writing it back into the repo
- `trans_install`: merge repo content with selected live-only state

## Use Case 1: Strip Noise On Update, Preserve The Same Noise On Install

This is the standard round-trip pattern for noisy local state.

Desired result:

- repo file stays clean
- live file keeps selected local-only state

Configuration shape:

1. `trans_update`: use `--strip-*` with selector list `A`
2. `trans_install`: use the same selector list `A`, but as `--retain-*`

Meaning:

- update removes `A` from the live file before saving into the repo
- install starts from the repo file, then copies `A` back from the live file

This pattern works directly when the transform engine is base-authoritative in
merge mode and selectors target the overlay operand.

That is the current TOML and XML behavior.

Example shape:

```yaml
trans_update: some_transform "--strip-key A"
trans_install: some_transform "--overlay-file '{{@@ _dotfile_abs_dst @@}}' --retain-key A"
```

## Use Case 2: Keep Only A Retained Subset On Update

This is a different workflow.

Desired result:

- repo file stores only retained subset `B`
- repo intentionally becomes a reduced representation of the live file

Configuration shape:

1. `trans_update`: use `--retain-*` with selector list `B`

Meaning:

- update writes only `B` from the live file back into the repo

This part is valid on its own.

## Important Limitation For Install

The install half you described was:

- `trans_update`: retain list `B`
- `trans_install`: retain whole repo file as overlay on top of the live file

That is a valid desired workflow, but it is not the merge direction provided by
the current TOML engine.

Current TOML merge behavior:

- base is authoritative
- selectors target the overlay
- selected overlay content is copied onto the base

So TOML currently supports:

- "repo base + selected live overlay"

It does not currently support:

- "live base + selected repo overlay"

If you want that second install direction, the engine would need explicit
support for the opposite merge direction or separate engine-specific selector
flags for both operands.

## Practical Rule

Use Case 1 is the safe default for noisy live state.

Use Case 2 is only fully round-trippable if the engine's merge direction matches
the install behavior you want.

## Where To Look Next

- TOML specifics:
  [toml-transform.md](/Users/xian/Projects/dotfiles/docs/toml-transform.md)
- XML specifics:
  [xml-transform.md](/Users/xian/Projects/dotfiles/docs/xml-transform.md)
- plist specifics:
  [plist-transform.md](/Users/xian/Projects/dotfiles/docs/plist-transform.md)

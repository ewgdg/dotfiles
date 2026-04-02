# Transform CLI Interface

This document defines the shared CLI contract used by the format-specific
transform scripts in this repo.

It is the reference contract for the current transform CLI redesign.

The Python-side engine contract lives in
[transform-engine-interface.md](transform-engine-interface.md).
For format-specific selector syntax, see the individual format docs.

## Standard CLI Shape

```sh
script BASE OUTPUT \
  --mode cleanup|merge \
  [--overlay-file OVERLAY] \
  [--selector-type remove|retain] \
  [--selectors SELECTORS...] \
  [ENGINE-DECLARED EXTRA FLAGS]
```

- `BASE`: primary operand. Selectors always apply to this file.
- `OUTPUT`: transformed output path.
- `--mode cleanup`: write a filtered view of `BASE`.
- `--mode merge`: preserve a filtered view of `BASE`, then apply `OVERLAY`
  on top of it.
- `--overlay-file`: secondary operand. Required in merge mode.

In the intended dotdrop round-trip workflow, `BASE` is the current live file
for `trans_install`, and `OVERLAY` is the repo file being reapplied.

## Goal

The round-trip workflow should do all of the following:

- keep the repo intentionally managed
- preserve unmanaged live-only state
- reflect repo edits and deletions back into live files on install

## Shared Semantics

For a selector set `S`:

| Mode | `retain` | `remove` |
| --- | --- | --- |
| `cleanup` | `output = retain_S(BASE)` | `output = remove_S(BASE)` |
| `merge` | `output = overlay(retain_S(BASE), OVERLAY)` | `output = overlay(remove_S(BASE), OVERLAY)` |

Selectors always partition `BASE`.
`OVERLAY` is never the selector target in the shared contract.

`overlay()` only writes content that exists in `OVERLAY`.
Deletions are reflected because the repo-managed region has already been
removed from `BASE` before `OVERLAY` is applied.

## Round-Trip Rule

For a paired `trans_update` and `trans_install`:

- reuse the same selector set for both steps
- flip `--selector-type` between cleanup and merge

That gives a stable partition/recompose workflow:

```text
managed_live = cleanup_with_update_rules(live_current)
preserved_live = live_current - managed_live
live_next = overlay(preserved_live, repo_current)
```

This is the core mental model:

- `trans_update` decides which part of the live file becomes repo-managed
- `trans_install` preserves the complementary live residue
- `trans_install` then reapplies the repo file on top

If the repo deletes something inside the repo-managed region, that deletion is
preserved on install because the old managed content was discarded before the
repo file was overlaid.

## Standard Round-Trip Patterns

### 1. Remove noisy live-only state from the repo

Use this when the repo should contain everything except a noisy local subset
`A`.

```text
trans_update: cleanup remove A
trans_install: merge retain A
```

Meaning:

- update writes `live - A` into the repo
- install preserves `A` from the current live file
- install then overlays the repo file onto that preserved residue

### 2. Keep only a managed subset in the repo

Use this when the repo should store only subset `B`.

```text
trans_update: cleanup retain B
trans_install: merge remove B
```

Meaning:

- update writes only `B` into the repo
- install removes `B` from the current live file
- install then overlays the repo file onto the unmanaged residue

## Why Deletions Work

Assume:

```text
repoA = cleanup(liveA)
repoB = edit(repoA)
managed_live = cleanup_with_update_rules(liveA)
preserved_live = liveA - managed_live
liveB = overlay(preserved_live, repoB)
```

If `repoB` deletes a nested entry that existed in `repoA`, that entry is still
removed from `liveB`.
It does not survive from `liveA`, because it belonged to the managed partition
that was discarded before `repoB` was applied.

This is the key property the redesign is trying to preserve.

## Selector Model

- `--selector-type` chooses whether the matched region of `BASE` is preserved
  or removed
- `--selectors` passes engine-specific matchers to the target engine
- selector syntax is format-specific, but operand roles are not

Examples:

- `--selector-type retain --selectors 'model' 're:^projects\.'`
- `--selector-type remove --selectors 'config/WindowGeometry'`

## Design Rules

- selectors target `BASE` in both modes
- merge semantics are shared across engines
- engines may differ in selector vocabulary and structural merge rules, but not
  in which operand selectors target
- `--compare-file` is for serialization stability only and does not change the
  semantic result
- each format doc must document identity rules for repeated or nested
  structures, plus any unsupported cases

## Dotdrop Note

For the redesigned install flow, the merge engine should be invoked with the
current live file as `BASE` and the repo file as `OVERLAY`.
If the dotdrop action wrappers still pass those operands in the old order, they
need to be updated to match this contract.

# Transform CLI Interface

This document defines the shared CLI contract used by the format-specific
transform scripts in this repo.

The Python-side engine contract that sits behind the CLI is documented in
[`docs/transform-engine-interface.md`](/Users/xian/Projects/dotfiles/docs/transform-engine-interface.md).
For round-trip workflow examples, see
[`docs/transform-cli-usage.md`](/Users/xian/Projects/dotfiles/docs/transform-cli-usage.md).

## Standard CLI Shape

```sh
script INPUT OUTPUT \
  --mode strip|merge \
  [--overlay-file OVERLAY] \
  [--selector-type remove|retain] \
  [--selectors SELECTORS...] \
  [ENGINE-DECLARED EXTRA FLAGS]
```

- `INPUT`: base file
- `OUTPUT`: transformed output path
- `--mode cleanup`: transform the base file directly
- `--mode merge`: combine base and overlay using engine-defined merge semantics
- `--overlay-file`: required in merge mode

## Selector Model

Selectors define both what matchers apply and the action applied.

- `--selector-type`: action to apply on grouped matchers (`retain` or `remove`).
- `--selectors`: a list of matchers, optionally prefixed (like `re:` or `exact:`), which are routed to the target engine's implementations.

Examples:

- `--selector-type retain --selectors 'model' 're:^projects\.'`
- `--selector-type remove --selectors 'config/WindowGeometry'`

Selector action meaning:

- `retain`
  - cleanup mode: write only matching content from the base file
  - merge mode: apply only matching content from the engine-selected operand
- `remove`
  - cleanup mode: remove matching content from the base file
  - merge mode: apply everything except matching content from the
    engine-selected operand

The mode name and selector action are independent. For example:

- `--mode cleanup` with `--selector-type retain` means "write only the retained subset
  from the base file"
- `--mode merge` with `--selector-type remove` means "merge everything except the
  removed subset from the selected merge operand"

## Operand Roles

The CLI only guarantees operand positions:

- `INPUT` is the base operand
- `--overlay-file` is the overlay operand

Which operand selectors target in merge mode is engine-defined and must be
documented by each format-specific transform doc.

Common merge shapes in this repo:

- base-authoritative merge: start from `INPUT` and apply selected overlay
  content onto it
- overlay-authoritative merge: start from `--overlay-file` and apply selected
  base content onto it

## Design Rules

- Keep `INPUT` and `OUTPUT` positional and in that order.
- Use `--overlay-file` for merge-mode live state.
- Keep retain vs strip selector actions mutually exclusive per invocation.
- Document selector targeting for merge mode in each engine doc.
- If an engine supports selectorless operation, document that explicitly.

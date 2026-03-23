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
  [ENGINE-DECLARED EXTRA FLAGS] \
  [ENGINE-DECLARED SELECTOR FLAGS]
```

- `INPUT`: base file
- `OUTPUT`: transformed output path
- `--mode strip`: transform the base file directly
- `--mode merge`: combine base and overlay using engine-defined merge semantics
- `--overlay-file`: required in merge mode

## Selector Model

Selectors combine:

- an action: `retain` or `strip`
- an engine-defined selector type such as `key`, `table-regex`, or
  `node-matcher`

Examples:

- `--retain-key`
- `--strip-key`
- `--retain-table-regex`
- `--strip-node-matcher`

All selector flags in one invocation must use the same action.

Selector action meaning:

- `retain`
  - strip mode: write only matching content from the base file
  - merge mode: apply only matching content from the engine-selected operand
- `strip`
  - strip mode: remove matching content from the base file
  - merge mode: apply everything except matching content from the
    engine-selected operand

The mode name and selector action are independent. For example:

- `--mode strip` with `--retain-key ...` means "write only the retained subset
  from the base file"
- `--mode merge` with `--strip-key ...` means "merge everything except the
  stripped subset from the selected merge operand"

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

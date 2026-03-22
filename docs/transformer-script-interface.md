# Transformer Script Interface

Future transform scripts in this repo should follow a shared CLI design so
`trans_update` and `trans_install` stay predictable across file formats.

The Python-side engine contract that should sit behind that CLI is documented in
[`docs/transform-engine-interface.md`](/Users/xian/Projects/dotfiles/docs/transform-engine-interface.md).

## Standard CLI Shape

```sh
script INPUT OUTPUT \
  --mode strip|merge \
  [--overlay-file OVERLAY] \
  [ENGINE-DECLARED EXTRA FLAGS] \
  [ENGINE-DECLARED SELECTOR FLAGS]
```

- `INPUT`: the base file
- `OUTPUT`: the transformed output path
- `--mode strip`: transform the base file directly
- `--mode merge`: combine the base file and overlay file using engine-defined
  merge semantics
- `--overlay-file`: required in merge mode
- engines may declare additional format-specific flags
- selector flags are declared by the engine via `SelectorSpec`
- selector flags may be optional if the engine explicitly allows identity
  transforms

## Selector Semantics

The shared CLI should generate typed selector flags by combining:

- a selector action: `retain` or `strip`
- an engine-declared selector type such as `key` or `table-regex`

Examples:

- `--retain-key`
- `--strip-key`
- `--retain-table-regex`
- `--strip-table-regex`

All selector flags in a single invocation must use the same action:

- `retain`:
  - strip mode: write only matching content from the base file
  - merge mode: apply engine-defined merge behavior using only matching content
- `strip`:
  - strip mode: remove matching content from the base file
  - merge mode: apply engine-defined merge behavior after removing matching
    content

## Matcher Syntax

Each transformer can define its own matcher grammar, but the contract should be
explicit in that transformer's format-specific doc.

The TOML transformer is the reference example:

- `--retain-key` / `--strip-key` target exact TOML key paths
- `--retain-table-regex` / `--strip-table-regex` target whole tables by regex

The XML transformer follows the same contract:

- `--retain-node-matcher` / `--strip-node-matcher` target `fnmatch`-style XML
  node paths
- `--sort-attributes` is an engine-specific flag, not a selector

The plist transformer also follows the contract:

- `--retain-key` / `--strip-key` target top-level plist dictionary keys
- selector flags are optional, so compare-only format conversion can still use
  the shared CLI

## Design Rules

- Keep `INPUT` and `OUTPUT` positional and in that order.
- Use `--overlay-file` for merge-mode live state instead of introducing
  format-specific synonyms.
- Keep retain vs strip selector actions mutually exclusive per invocation.
- Apply typed selector flags in both strip and merge mode.
- If an engine allows selectorless operation, define and document the no-selector
  behavior explicitly.
- Prefer allowlist semantics for durable config when both strip and retain are
  possible.

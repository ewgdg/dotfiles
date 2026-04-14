# JSON Transform

`scripts/json_transform.py` powers the JSON cleanup/merge helpers used by
package target commands in this repo.

Shared CLI semantics live in
[transform-cli-interface.md](transform-cli-interface.md).

## Selector Types

The JSON engine exposes one selector type:

- default `exact:` selector: exact top-level JSON object key

Examples:

- `buildDir`
- `version`

JSON-specific notes:

- selectors operate on top-level object keys only
- selectorless operation is allowed
- with no selectors, cleanup is identity and merge starts from the whole base
  JSON object before applying the overlay object

## Merge Semantics

The JSON engine follows the shared contract:

- selectors always target the base JSON object
- merge preserves the selected or complementary top-level keys from the base
  object, depending on `--selector-type`
- the overlay JSON object is then applied on top

Because selectors work at top-level key granularity, nested deletions are
reflected by replacing the entire selected key from the overlay object.

## Structural Notes

- top-level key identity is exact string equality
- when a selected key exists in both operands, the overlay value replaces the
  preserved base value for that key
- when a selected key was removed from the repo, it stays removed after install
  because that top-level key was already excluded from the preserved base
  partition
- JSON output is serialized with tab indentation unless `--compare-file` lets
  the engine reuse existing semantically equivalent text

## Engine-Specific Flags

The JSON engine also supports:

- `--compare-file PATH`

`--compare-file` is opt-in.
When provided, the engine reuses that file's existing text if its parsed JSON
matches the transformed data, which avoids no-op rewrites caused by JSON
serialization.
Without `--compare-file`, the engine always serializes fresh output.

## Example

```sh
uv run scripts/json_transform.py live.json output.json \
  --mode merge \
  --overlay-file repo.json \
  --selector-type retain \
  --selectors 'buildDir' 'version'
```

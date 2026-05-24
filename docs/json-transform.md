# JSON Transform

`scripts/json_transform.py` powers the JSON cleanup/merge helpers used by
package target commands in this repo.

Shared CLI semantics live in
[transform-cli-interface.md](transform-cli-interface.md).

## Selector Types

The JSON engine exposes these selector types:

- default `exact:` selector: exact JSON object key path
- `re:` selector: regex matching dotted JSON object key paths

Examples:

- `buildDir`
- `settings.window.width`
- `"settings.window".width`
- `re:^Window`
- `re:^settings\.window\.`

JSON-specific notes:

- regex selectors operate on dot-joined JSON object key paths
- exact key paths use dot-separated object keys
- quote a key path part when the literal JSON key contains a dot, for example
  `"settings.window".width`
- exact key paths traverse JSON objects only; arrays are treated as normal
  values, not as indexable path segments
- regex selectors match key path text with Python `re.search`
- selectorless operation is allowed
- with no selectors, cleanup is identity and merge starts from the whole base
  JSON object before applying the overlay object

## Merge Semantics

The JSON engine follows the shared contract:

- selectors always target the base JSON object
- merge preserves the selected or complementary key paths from the base object,
  depending on `--selector-type`
- the overlay JSON object is then applied on top
- for keys that survive from live or repo input, merge keeps live object key
  order where possible and appends repo-only keys in repo order

For top-level selectors, overlay values replace preserved base values at that
key. For nested exact or regex selectors, overlay is applied recursively along
the selected key path ancestors so unselected sibling keys can survive install.

## Structural Notes

- key path part identity is exact string equality
- when a selected top-level key exists in both operands, the overlay value
  replaces the preserved base value for that key
- when a selected nested key was removed from the repo, it stays removed after
  install because that key path was already excluded from the preserved base
  partition
- JSON output is serialized with detected indentation from `--compare-file`,
  base file, or overlay file; if no indentation can be detected, it falls back
  to two spaces

## Engine-Specific Flags

The JSON engine also supports:

- `--compare-file PATH`

`--compare-file` is opt-in.
When provided, the engine reuses that file's existing text if its parsed JSON
matches the transformed data, which avoids no-op rewrites caused by JSON
serialization.
Without `--compare-file`, the engine always serializes fresh output while
reusing indentation from the base or overlay file when detectable.

## Example

```sh
uv run scripts/json_transform.py live.json output.json \
  --mode merge \
  --overlay-file repo.json \
  --selector-type retain \
  --selectors 'buildDir' 'settings.window.width'
```

# XML Transform

`scripts/xml_transform.py` powers the XML-based cleanup/merge helpers used by
package target commands in this repo.

Shared CLI semantics live in
[transform-cli-interface.md](transform-cli-interface.md).

## Selector Types

The XML engine exposes these selector types:

- default `exact:` selector: `fnmatch`-style XML node path matcher
- `re:` selector: regex matching XML node paths

Examples:

- `config/WindowGeometry`
- `config/*WindowState`
- `re:^config/Window`

XML-specific notes:

- selectors match node paths, not raw text fragments
- `retain` in cleanup mode preserves the root element and any required ancestor
  chain for retained descendants
- selectorless operation is not supported

## Merge Semantics

The XML engine follows the shared contract:

- selectors always target the base XML tree
- merge preserves the selected or complementary region from the base tree,
  depending on `--selector-type`
- the overlay XML tree is then applied on top

This gives the intended round-trip behavior:

- unmanaged live-only XML survives install
- repo-side deletions survive install because the managed XML region was
  removed from the base side before the overlay tree was applied

## Structural Notes

- repeated siblings are matched by tag plus lightweight identity hints when
  available
- the current XML identity hints are `id`, `name`, `key`, `uuid`, and
  non-empty text content
- path matching uses `fnmatch`-style globs for default/exact selectors
- regex selectors match paths with Python `re.search`
- nested deletions inside a managed subtree are reflected when the repo subtree
  replaces the discarded base subtree

## Engine-Specific Flags

The XML engine also supports:

- `--compare-file PATH`
- `--sort-attributes`
- `--sort-children NODE_PATH`

`--compare-file` is opt-in.
When provided, the engine reuses that file's bytes if its parsed XML is
semantically unchanged after the transform.
Without `--compare-file`, the engine always writes fresh output.

`--sort-children` canonically sorts the immediate children of matching parent
paths. This is useful for XML lists that behave like sets in the application,
such as GoldenDict NG's `config/mutedDictionaries`, where sibling order may
churn even when the effective content is unchanged.

## Example

```sh
uv run scripts/xml_transform.py live.xml output.xml \
  --mode merge \
  --overlay-file repo.xml \
  --sort-children 'config/mutedDictionaries' \
  --selector-type retain \
  --selectors 'config/WindowGeometry'
```

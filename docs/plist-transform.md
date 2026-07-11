# Plist Transform

`dotman transform plist` powers plist-based cleanup/merge target commands in
this repo. `scripts/plist_transform.py` remains temporarily for legacy callers
until its removal in issue #16.

Shared CLI semantics live in
[transform-cli-interface.md](transform-cli-interface.md).

## Selector Types

The plist engine exposes these selector types:

- default `exact:` selector: exact plist dictionary key path
- `re:` selector: regex matching dotted plist dictionary key paths

Examples:

- `NSUserKeyEquivalents`
- `bypassEventsFromOtherApplications`
- `settings.window.width`
- `"settings.window".width`
- `re:^NSWindow`
- `re:^widget\.[^.]+\.enabled$`

Plist-specific notes:

- exact selectors use dot-separated dictionary key paths
- quote a path part when the literal plist key contains a dot
- regex selectors use Python `re.search` against complete dotted key paths
- matching a dictionary path selects the whole dictionary subtree
- arrays are treated as atomic values, not indexable path segments
- selectorless operation is allowed
- with no selectors, cleanup is identity and merge starts from the whole base
  plist before applying the overlay plist

## Merge Semantics

The plist engine follows the shared contract:

- selectors always target the base plist
- merge preserves the selected or complementary key paths from the base plist,
  depending on `--selector-type`
- the overlay plist is then applied on top

For top-level selectors, overlay values replace preserved base values at that
key. For nested selectors, overlay is applied recursively along the selected
key path ancestors so unselected sibling keys can survive install.

## Structural Notes

- dictionary key identity is exact string equality
- when a selected top-level key exists in both operands, the overlay value
  replaces the preserved base value for that key
- when a selected nested key was removed from the repo, it stays removed after
  install because that path was already excluded from the preserved base
  partition
- plist arrays and scalar values are replaced as whole values

## Engine-Specific Flags

The plist engine also supports:

- `--output-format xml|binary`
- `--compare-file PATH`

`--compare-file` is opt-in.
When provided, the engine reuses that file's existing bytes if its parsed plist
matches the transformed data, which avoids no-op rewrites caused by
`plistlib` serialization.
Without `--compare-file`, the engine always serializes fresh output in the
requested format.

## Example

```sh
dotman transform plist live.plist output.plist \
  --mode merge \
  --overlay-file repo.plist \
  --output-format binary \
  --selector-type remove \
  --selectors 'NSUserKeyEquivalents'
```

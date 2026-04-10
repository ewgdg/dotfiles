# Plist Transform

`scripts/plist_transform.py` powers the plist-based cleanup/merge helpers used
by package target commands in this repo.

Shared CLI semantics live in
[transform-cli-interface.md](transform-cli-interface.md).

## Selector Types

The plist engine exposes one selector type:

- default `exact:` selector: exact top-level plist dictionary key

Examples:

- `NSUserKeyEquivalents`
- `bypassEventsFromOtherApplications`

Plist-specific notes:

- selectors operate on top-level dictionary keys only
- selectorless operation is allowed
- with no selectors, cleanup is identity and merge starts from the whole base
  plist before applying the overlay plist

## Merge Semantics

The plist engine follows the shared contract:

- selectors always target the base plist
- merge preserves the selected or complementary top-level keys from the base
  plist, depending on `--selector-type`
- the overlay plist is then applied on top

Because plist selectors work at top-level key granularity, nested deletions are
reflected by replacing the entire selected key from the overlay plist.

## Structural Notes

- top-level key identity is exact string equality
- when a selected key exists in both operands, the overlay value replaces the
  preserved base value for that key
- when a selected key was removed from the repo, it stays removed after install
  because that top-level key was already excluded from the preserved base
  partition

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
python3 scripts/plist_transform.py live.plist output.plist \
  --mode merge \
  --overlay-file repo.plist \
  --output-format binary \
  --selector-type remove \
  --selectors 'NSUserKeyEquivalents'
```

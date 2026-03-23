# Plist Transform Selectors

`scripts/plist_transform.py` powers the plist-based dotdrop transforms in
`config.yaml`.

Shared CLI semantics live in
[`docs/transform-cli-interface.md`](/Users/xian/Projects/dotfiles/docs/transform-cli-interface.md).

## Selector Types

The plist engine exposes one typed selector flag:

- `--retain-key` / `--strip-key`: exact top-level plist dictionary key

Plist-specific details:

- selectors target only top-level dictionary keys
- selectorless operation is allowed
- without selectors, the transform operates on the whole plist

## Merge Direction

In merge mode, the plist engine is overlay-authoritative:

- start from the overlay plist
- selectors target the base plist
- selected base keys are copied onto the overlay

## Engine-Specific Flags

The plist engine also supports:

- `--output-format xml|binary`
- `--compare-file PATH`

`--compare-file` preserves the existing file bytes when the transformed plist is
semantically unchanged, which avoids no-op rewrites caused by `plistlib`
serialization.

## Example

```sh
python3 scripts/plist_transform.py base.plist output.plist \
  --mode merge \
  --overlay-file live.plist \
  --output-format binary \
  --retain-key NSUserKeyEquivalents \
  --retain-key AppleInterfaceStyle
```

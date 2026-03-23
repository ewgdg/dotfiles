# XML Transform Selectors

`scripts/xml_transform.py` powers the `xml_transform_strip` and
`xml_transform_merge` dotdrop transforms.

Shared CLI semantics live in
[`docs/transform-cli-interface.md`](/Users/xian/Projects/dotfiles/docs/transform-cli-interface.md).

## Selector Types

The XML engine exposes one typed selector flag:

- `--retain-node-matcher` / `--strip-node-matcher`: `fnmatch`-style XML node
  path matcher

The matcher syntax is the existing root-relative slash path, for example:

- `config/WindowGeometry`
- `config/*WindowState`
- `config/timeForNewReleaseCheck`

Comma-separated matcher lists are accepted for compatibility, but repeated or
space-separated values are preferred.

XML-specific details:

- retain mode preserves the root element and any required ancestor chain
- merge mode is base-authoritative
- selectors target the overlay XML during merge

## Engine-Specific Flags

The XML engine also supports:

- `--sort-attributes`

The transform preserves original base or overlay bytes automatically when the
result is semantically unchanged, so there is no separate opt-in flag for that.

## Example

```sh
python scripts/xml_transform.py base.xml output.xml \
  --mode merge \
  --overlay-file live.xml \
  --retain-node-matcher config/WindowGeometry config/WindowState
```

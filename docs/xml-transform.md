# XML Transform Selectors

`scripts/xml_transform.py` powers the `xml_transform_strip` and
`xml_transform_merge` dotdrop transforms.

It follows the standardized transformer selector interface documented in
`docs/transformer-script-interface.md`.

## Selector Types

The XML engine currently exposes one typed selector flag:

- `--retain-node-matcher` / `--strip-node-matcher`: `fnmatch`-style XML node
  path matcher

The matcher syntax is the existing root-relative slash path, for example:

- `config/WindowGeometry`
- `config/*WindowState`
- `config/timeForNewReleaseCheck`

Comma-separated matcher lists are accepted for compatibility, but repeated or
space-separated values are preferred.

## Strip Mode

`--mode strip` operates on the base XML file:

- `--strip-node-matcher` removes matching nodes from the base file.
- `--retain-node-matcher` writes only matching nodes, while preserving the root
  element and any necessary ancestor chain.

## Merge Mode

`--mode merge` keeps the base XML authoritative and filters the overlay file
named by `--overlay-file` before merging it:

- `--retain-node-matcher` merges only matching overlay nodes.
- `--strip-node-matcher` merges all overlay content except matching nodes.

The XML engine also supports one format-specific flag:

- `--sort-attributes`

The transform preserves original base or overlay bytes automatically when the
result is semantically unchanged, so there is no separate opt-in flag for that.

```sh
python scripts/xml_transform.py base.xml output.xml \
  --mode merge \
  --overlay-file live.xml \
  --retain-node-matcher config/WindowGeometry config/WindowState
```

The first positional path is always the base file. In install mode that is the
repo XML. `--overlay-file` points at the live XML, and the selector flag
decides which live nodes participate in the merge.

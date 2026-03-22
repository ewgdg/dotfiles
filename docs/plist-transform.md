# Plist Transform Selectors

`scripts/plist_transform.py` powers the plist-based dotdrop transforms in
`config.yaml`.

It follows the standardized transformer selector interface documented in
`docs/transformer-script-interface.md`.

## Selector Types

The plist engine currently exposes one typed selector flag:

- `--retain-key` / `--strip-key`: exact top-level plist dictionary key

Unlike the TOML and XML engines, plist selectors are optional. If you omit
selector flags entirely, the transform operates on the whole plist. That keeps
plain format-conversion and compare-only workflows on the shared CLI.

## Strip Mode

`--mode strip` operates on the base plist file:

- `--retain-key` writes only matching keys.
- `--strip-key` removes matching keys.
- no selector flags write the whole base plist.

## Merge Mode

`--mode merge` keeps the overlay plist authoritative as the container file and
applies filtered base plist keys on top of it. This matches the plist use case
in this repo: preserve unmanaged live preferences while forcing a managed subset
from the repo.

- `--retain-key` applies only matching base keys onto the overlay plist.
- `--strip-key` applies all base keys except matching ones onto the overlay
  plist.
- no selector flags apply the whole base plist onto the overlay plist.

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

The first positional path is always the base file. In install mode that is the
repo plist. `--overlay-file` points at the live plist, and the selector flag
filters which repo keys get layered onto that live plist.

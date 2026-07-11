# TOML Transform

`dotman transform toml` powers TOML cleanup/merge commands in this repo.
The older `scripts/toml_transform.py` implementation remains temporarily for
non-migrated generic transform work and will be removed under issue #16.

Shared CLI semantics live in
[transform-cli-interface.md](transform-cli-interface.md).

## Selector Types

The TOML engine exposes these selector types:

- default `exact:` selector: exact TOML key path
- `re:` selector: regex matching dotted TOML table or key paths

Examples:

- `model`
- `mcp_servers.playwright.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN`
- `re:^projects\.`
- `re:^mcp_servers\.playwright\.env$`
- `re:^widget\.[^.]+\.enabled$`

TOML-specific notes:

- exact selectors match exact dotted TOML key paths
- regex selectors use Python `re.search` against dotted table and key paths
- matching a table path selects the whole table
- matching a key path selects only that key
- selectorless operation is not supported

## Merge Semantics

The TOML engine follows the shared contract:

- selectors always target the base TOML document
- merge preserves the selected or complementary region from the base document,
  depending on `--selector-type`
- the overlay TOML document is then applied on top

This gives the intended round-trip behavior:

- unmanaged live residue survives install
- repo-managed deletions survive install because the managed region was removed
  from the base side before the overlay document was applied

## Structural Notes

- overlaying tables is recursive
- if a managed key or table was removed from the repo, it stays removed after
  install because it was already excluded from the preserved base partition
- array or collection semantics should be treated according to normal TOML value
  replacement, not implicit element-level merging

## Engine-Specific Flags

The TOML engine also supports:

- `--compare-file PATH`

`--compare-file` is opt-in.
When provided, the engine may reuse that file's exact text if it already
matches the transformed document.
`--compare-file` is a serialization-stability optimization only; it must not
change the semantic result.
Without `--compare-file`, the engine may still preserve untouched base-region
formatting or comments when the TOML writer can patch those regions in place,
but changed managed regions may still be serialized fresh.

## Example

```sh
dotman transform toml live.toml output.toml \
  --mode merge \
  --overlay-file repo.toml \
  --selector-type retain \
  --selectors 'mcp_servers.playwright.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN' \
  're:^mcp_servers\.playwright\.env$'
```

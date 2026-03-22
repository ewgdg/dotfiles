# TOML Transform Selectors

`scripts/toml_transform.py` powers the `toml_transform_strip` and
`toml_transform_merge`
dotdrop transforms.

It follows the standardized transformer selector interface documented in
`docs/transformer-script-interface.md`.

## Selector Types

The TOML engine currently exposes these typed selector flags:

- `--retain-key` / `--strip-key`: exact TOML key path
- `--retain-table-regex` / `--strip-table-regex`: regex against dotted table
  path

All selector flags in a single invocation must use the same action:

- `retain`: keep only matching content
- `strip`: remove matching content

## Strip Mode

`--mode strip` operates on the base TOML file:

- `--strip-key` and `--strip-table-regex` remove matching keys and tables from
  the base file.
- `--retain-key` and `--retain-table-regex` write only matching keys and tables
  from the base file.

## Merge Mode

`--mode merge` keeps the base TOML authoritative and filters the overlay file
named by `--overlay-file` before applying it:

- `--retain-key` and `--retain-table-regex` merge only matching overlay keys
  and tables.
- `--strip-key` and `--strip-table-regex` merge all overlay content except
  matching keys and tables.

## Example

```sh
uv run --project . scripts/toml_transform.py input.toml output.toml \
  --mode merge \
  --overlay-file live.toml \
  --retain-key model mcp_servers.playwright.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN \
  --retain-table-regex '^mcp_servers\.playwright\.env$'
```

The first positional path is always the base file. In install mode that is the
repo TOML. `--overlay-file` points at the live TOML. The selector flag decides
which overlay content participates in the merge.

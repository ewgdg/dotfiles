# TOML Transform Selectors

`scripts/toml_transform.py` powers the `toml_transform_strip` and
`toml_transform_merge` dotdrop transforms.

Shared CLI semantics live in
[`docs/transform-cli-interface.md`](/Users/xian/Projects/dotfiles/docs/transform-cli-interface.md).

## Selector Types

The TOML engine exposes these typed selector flags:

- `--retain-key` / `--strip-key`: exact TOML key path
- `--retain-table-regex` / `--strip-table-regex`: regex against dotted table
  path

All selector flags in a single invocation must use the same action:

- `retain`: select only matching content
- `strip`: exclude matching content

TOML-specific details:

- key selectors match exact dotted TOML key paths
- table regex selectors match whole tables, not one nested key inside a table
- selectorless operation is not supported

## Operand Roles

In merge mode, the TOML engine is base-authoritative:

- start from the base TOML
- selectors target the overlay TOML
- selected overlay content is copied onto the base

That makes it a good fit for repo-base plus preserved-live-subset installs.

## Example

```sh
uv run --project . scripts/toml_transform.py repo.toml output.toml \
  --mode merge \
  --overlay-file live.toml \
  --retain-key model mcp_servers.playwright.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN \
  --retain-table-regex '^mcp_servers\.playwright\.env$'
```

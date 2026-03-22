# TOML Transform Selectors

`scripts/toml_transform.py` powers the `toml_strip_keys` and `toml_merge_keys`
dotdrop transforms.

## Strip Mode

`--mode strip` removes explicit key matchers from the
base TOML file before writing it back into the repo.

## Merge Mode

`--mode merge` keeps the repo file authoritative and overlays selected live
values back into the install output via `--overlay-file`.

Merge key matchers use the same syntax as strip mode:

- Plain matchers preserve exact key paths.
- `re:` matchers preserve matching tables from the live file.

```sh
uv run --project . scripts/toml_transform.py input.toml output.toml \
  --mode merge \
  --overlay-file live.toml \
  model \
  'mcp_servers.playwright.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN' \
  're:^mcp_servers\.playwright\.env$'
```

The first positional path is always the base file. In install mode that is the
repo TOML. `--overlay-file` points at the live TOML, and the key matchers
describe which overlay values should be retained.

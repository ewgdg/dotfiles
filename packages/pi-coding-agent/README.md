# Pi coding agent

## MCP servers

Pi has built-in MCP support (`builtin:mcp`); no extension package is needed.
See the upstream [MCP docs](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md).

Global server definitions live in `~/.pi/agent/mcp.json` under `mcpServers` and
are tracked here. Trusted projects can add or override servers in `.pi/mcp.json`.
Manage servers with `pi mcp add` or file edits. Keep credentials out of the file:
use `${ENV_VAR}` references, `!command` values, or OAuth sign-in.

- `/mcp` inspects connections, signs in, and changes exposure or enabled state.
- `/reload` picks up config edited outside the session; `pi mcp list` validates it.
- Exposure: the model reaches non-`direct` tools through `codemode` scripts or
  `tool_search`. This config enables `codemode` by default (`defaultTools`).

OAuth tokens (`mcp-auth.json`) and the server log (`mcp.log*`) stay untracked.

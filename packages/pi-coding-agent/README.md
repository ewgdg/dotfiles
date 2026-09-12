# Pi coding agent

## MCP servers

[`pi-mcp-client`](https://github.com/mavam/pi-mcp-client) provides MCP discovery
and native tool activation. It requires Pi 0.85.1+ and Node.js 22+.

Global server definitions live in `~/.pi/agent/mcp.json`, using the `mcpServers`
object. Trusted projects can override individual servers in `.mcp.json`.
See the upstream [configuration guide](https://github.com/mavam/pi-mcp-client/blob/main/docs/configuration.md).

Pi uses its own explicit server definitions, managed with `/mcp add` or file edits.
Server definitions are tracked; use environment references or secret commands
rather than committing credentials.

Restart Pi after changing extension packages. Use `/mcp` to check connections
and `/mcp reload` after editing configuration. The model discovers tools through
`mcp_tools`, activates exact identifiers, then calls the activated native tools.
Tool catalogs under `~/.pi/agent/cache/` remain untracked.

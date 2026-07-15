# Claude Code through CLIProxyAPI

`claudex` sends Claude Code requests to the local CLIProxyAPI Docker service, which routes them through Codex OAuth.

## Ownership

- The services repository owns the CLIProxyAPI container, configuration, OAuth state, management page, and reverse-proxy route.
- This repository owns only the `claudex()` launcher in `packages/shell/files/config/zsh/agents.zsh`.
- `packages/codex` remains limited to Codex CLI configuration.

For service setup and operations, see `services/cli-proxy-api/README.md` in the services repository.

## Launcher policy

`claudex` uses the local loopback endpoint `http://127.0.0.1:8317` and maps Claude Code model tiers directly:

- Main: `gpt-5.6-sol`
- Sonnet: `gpt-5.6-terra`
- Haiku and background work: `gpt-5.6-luna`

`CLAUDE_CODE_SUBAGENT_MODEL` remains unset so subagents can inherit the main model or use their configured tier.

The HTTPS management URL is intentionally not the launcher endpoint: it exposes only management routes, while client API routes remain local-only.

## Web search

CLIProxyAPI translates Claude Code WebSearch requests to Codex native `web_search`. No WebSearch plugin is configured.

## Support boundary

Anthropic supports Claude Code gateways, but not non-Claude model backends. CLIProxyAPI supplies the Anthropic-compatible translation and Codex routing.

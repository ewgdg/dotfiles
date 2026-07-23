# Claude Code through CLIProxyAPI

`claudex` sends Claude Code requests to CLIProxyAPI over its private-network HTTPS route, which routes them through Codex OAuth.

## Ownership

- The services repository owns the CLIProxyAPI container, configuration, OAuth state, management page, and reverse-proxy route.
- This repository owns only the `claudex()` launcher in `packages/shell/files/config/zsh/agents.zsh`.
- `packages/codex` remains limited to Codex CLI configuration.

For service setup and operations, see `services/cli-proxy-api/README.md` in the services repository.

## Launcher policy

`claudex` uses `https://cliproxyapi.service.xianzzz.com` so the same launcher works across trusted devices. Caddy accepts client API requests only from LAN and Tailscale source addresses.

Claude Code model tiers map directly:

- Main: `gpt-5.6-sol`
- Sonnet: `gpt-5.6-terra`
- Haiku and background work: `gpt-5.6-luna`

`CLAUDE_CODE_SUBAGENT_MODEL` remains unset so subagents can inherit the main model or use their configured tier.

The raw port `8317` remains host-loopback-only. Cross-device clients connect through Caddy on the standard HTTPS port.

## Web search

CLIProxyAPI translates Claude Code WebSearch requests to Codex native `web_search`. No WebSearch plugin is configured.

## Support boundary

Anthropic supports Claude Code gateways, but not non-Claude model backends. CLIProxyAPI supplies the Anthropic-compatible translation and Codex routing.

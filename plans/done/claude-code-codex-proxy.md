# CLIProxyAPI Docker migration

## Outcome

CLIProxyAPI runs as the `cli-proxy-api` Compose service in the services repository. Its tracked configuration, OAuth state volume, management page, and Caddy route are owned there.

The dotfiles repository retains only `claudex()`, which uses the loopback API and maps:

- Main: `gpt-5.6-sol`
- Sonnet: `gpt-5.6-terra`
- Haiku/background: `gpt-5.6-luna`

`CLAUDE_CODE_SUBAGENT_MODEL` is intentionally unset. CLIProxyAPI provides native Claude↔Codex WebSearch translation without a plugin.

## Validation

- Docker Compose configuration validates.
- Native user service is disabled.
- Docker API responds on `127.0.0.1:8317`.
- Codex OAuth exposes Sol, Terra, and Luna.
- Caddy serves the password-protected management page at `cliproxyapi.service.xianzzz.com` and blocks public client API routes.

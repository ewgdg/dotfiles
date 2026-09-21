# DevSpace

DevSpace is a self-hosted MCP server that gives a ChatGPT connector (or another
MCP client) read, edit, search, and shell access inside allowed local project
roots. This package installs the CLI, tracks the non-secret configuration, and
mints the OAuth owner password on first push.

## Install and first push

`dotman push` installs `@waishnav/devspace` through the npm global prefix and
writes `~/.devspace/config.jsonc`. The `devspace_owner_token` target then writes
`~/.devspace/auth.json` when it is missing.

That owner password is what ChatGPT asks for on the connector approval page:

```sh
cat ~/.devspace/auth.json
```

It is a live-local secret. The file is never tracked and the hook reports only
the path, never the value. Start the server with `devspace serve`.

Run `devspace init` only if you want DevSpace's interactive setup instead; it
rewrites `config.jsonc` from its answers, so the repo copy has to be pushed again
afterwards.

## Managed and unmanaged paths

| Path | Owner |
| --- | --- |
| `~/.devspace/config.jsonc` | this package, copied verbatim |
| `~/.devspace/auth.json` | live-local secret, minted once by the hook |
| `~/.devspace/skills/`, `~/.devspace/worktrees/` | DevSpace managed |
| `~/.local/share/devspace` | DevSpace state (`storage.stateDir`) |

## Instruction resolution

`skills.agentDir` is pinned to `~/.agents`, so DevSpace loads `~/.agents/AGENTS.md`
as the user-global instruction file and also discovers skills from
`~/.agents/skills`. The default `agentDir` is `~/.codex`, which reaches the same
instructions only through the codex package's symlink; pinning the shared
directory keeps this package independent of that symlink.

DevSpace loads context files with Pi's own `loadProjectContextFiles` and keeps the
global file plus the opened workspace's root context file. Nested context files
are listed for the client to read on demand instead of being loaded up front. Per
directory the first match wins among `AGENTS.override.md`, `AGENTS.md`,
`AGENTS.MD`, `CLAUDE.md`, and `CLAUDE.MD`.

## Public URL and tunnel

`server.publicBaseUrl` must be the public HTTPS origin without `/mcp`. DevSpace
does not create the tunnel: something has to forward to `127.0.0.1:7676` before a
ChatGPT connector can be added. `trustProxy` only changes which client IP is
recorded in logs.

The origin in this package is host-specific. Do not change it live with
`devspace config set publicBaseUrl`: the next push overwrites `config.jsonc` with
this copy, so record the value here instead.

## Why this target has no render or capture step

`config.jsonc` is JSONC, and `dotman transform json` rejects commented input, so
no selector-based render/capture can run against it. The target is a verbatim
copy: repo content is authoritative and live edits are overwritten on push. Move
any live change you want to keep back into `files/devspace/config.jsonc`.

## Security boundary

DevSpace contains file tools inside the configured roots, but its shell tool runs
as your user with no command policy. Keep `workspaces.allowedRoots` narrow and
treat a connected client as a trusted coding partner with access to this machine.

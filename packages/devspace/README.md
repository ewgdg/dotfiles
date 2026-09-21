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
| `~/.devspace/config.jsonc` | this package, rendered from a Jinja template |
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

The origin is a render-time var. DevSpace is installed on a single host, so the
package commits the tunnel origin as the default:

```toml
[vars.devspace]
public_base_url = "https://devspace.xianzzz.com"
```

Setting it empty renders `publicBaseUrl` as `null`, which is DevSpace's
local-only mode: the server then serves `127.0.0.1:7676` and advertises no public
origin, and only clients on this machine can complete OAuth. A second host
overrides the var in the untracked `~/.config/dotman/repos/<repo>/local.toml`
instead of editing that default.

## Service

`packages/linux/devspace` installs `~/.config/systemd/user/devspace.service` and
enables it. User scope matches the rest of this repo and needs no elevation, and
greetd autologins this account into niri at boot, so the user manager is always
present and the service starts without anyone logging in.

The unit starts the server with `fnm exec --using=default`, so the runtime is
whatever fnm's default node is. That matters because DevSpace depends on
`better-sqlite3`, whose native binding is built for the ABI of the node that ran
`npm`: this repo's shells use fnm (v22.23.1, ABI 127), while the inherited
`/usr/bin/node` is 26.x (ABI 147) and cannot load that binding at all — `serve`
fails outright with `NODE_MODULE_VERSION` mismatch rather than degrading.

Because the binding is ABI-bound, changing the fnm default node means rebuilding
DevSpace so the two agree:

```sh
npm rebuild -g better-sqlite3
```

## Templating

The tracked config is a Jinja source, and the target uses
`preset = "jinja-patch-editor"` to render it. The preset is used instead of a
selector transform because `config.jsonc` is JSONC and `dotman transform json`
rejects commented input.

## Security boundary

DevSpace contains file tools inside the configured roots, but its shell tool runs
as your user with no command policy. Keep `workspaces.allowedRoots` narrow and
treat a connected client as a trusted coding partner with access to this machine.

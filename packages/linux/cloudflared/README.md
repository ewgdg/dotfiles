# Cloudflare Tunnel

Publishes the DevSpace MCP server on `https://devspace.xianzzz.com` so the ChatGPT
connector can reach it. `packages/devspace` owns the server,
`packages/linux/devspace` owns its unit, and this package owns the tunnel in front
of it.

## What is tracked

- `files/cloudflared/config.yml` → `~/.cloudflared/config.yml`: ingress rules only.
- `files/config/systemd/user/cloudflared.service` → a user unit running
  `cloudflared tunnel run devspace`.

No tunnel UUID appears anywhere. The unit selects the tunnel by name, so
cloudflared resolves the name and finds its own credentials under
`~/.cloudflared`. A config needs `tunnel:` and `credentials-file:` only when the
name is not passed on the command line — which is exactly why upstream's
`service install` demands them.

The ingress `hostname` must equal `[vars.devspace] public_base_url` in
`packages/devspace`. DevSpace builds its OAuth discovery URLs from that origin, so
a mismatch produces a connector that reaches the tunnel and then cannot
authenticate.

## One-time manual steps

These are browser and account-API actions, so they are not automated. The
`cloudflared_tunnel_credentials` target detects their absence and fails the push
with the commands to run.

```sh
cloudflared tunnel login
cloudflared tunnel create devspace
cloudflared tunnel route dns devspace devspace.xianzzz.com
```

`~/.cloudflared/cert.pem` and `~/.cloudflared/<uuid>.json` are live-local secrets.
Neither is tracked, and nothing here reads their contents.

## Why a user unit

`cloudflared service install` writes a system unit as root and, unless
`--no-update-service` is passed, also installs a daily timer that runs
`cloudflared update` and restarts the service. On an Arch host pacman owns the
binary, so that timer would replace `/usr/bin/cloudflared` behind pacman's back.

The tracked unit runs unprivileged with `--no-autoupdate` instead, matching how
`packages/linux/devspace` runs the server. It uses `Type=exec` rather than
upstream's `Type=notify`: readiness reporting buys nothing here, and exec cannot
hang waiting for a notification that never arrives.

## Verifying

```sh
cloudflared --config ~/.cloudflared/config.yml tunnel ingress validate
cloudflared --config ~/.cloudflared/config.yml tunnel ingress rule https://devspace.xianzzz.com/mcp
systemctl --user status cloudflared
curl -sS -o /dev/null -w '%{http_code}\n' https://devspace.xianzzz.com/mcp
```

`--config` is a global flag, so it goes before the subcommand. `ingress validate`
reads any path, which is why the tracked file can be validated before a push. A
`401` from the last command means the tunnel and the server are both up.

## Notes

- The `service:` port is DevSpace's default (`7676`). If DevSpace's port changes,
  this ingress has to change with it.
- A wrong config or missing credentials makes the unit restart every 5s. Check
  `journalctl --user -u cloudflared` rather than assuming a network problem.
- Do not put a Cloudflare Access application in front of this hostname: it
  terminates the request before OAuth discovery reaches DevSpace.

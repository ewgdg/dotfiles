# Cloudflare Tunnel

Runs a Cloudflare Tunnel as a user service, publishing one local service on a public
hostname. The package is generic: what it publishes comes from `[vars.cloudflared]`
in the host profile that selects it.

## Variables

| var | meaning |
| --- | --- |
| `tunnel_name` | the named tunnel the unit runs |
| `hostname` | the public hostname to publish |
| `local_service` | the local origin, for example `http://127.0.0.1:8080` |

All three default to empty, so a host that selects this package without configuring
it fails the credentials probe instead of starting a unit that cannot run.

## What is tracked

- `files/cloudflared/config.yml` → `~/.cloudflared/config.yml`: ingress rules only.
- `files/config/systemd/user/cloudflared.service` → a user unit running
  `cloudflared tunnel run <tunnel_name>`.

Both render through the `jinja-patch-editor` preset, the same one `packages/ssh` and
`packages/git` use.

No tunnel UUID appears anywhere. The unit selects the tunnel by name, so cloudflared
resolves it and finds its own credentials under `~/.cloudflared`. A config needs
`tunnel:` and `credentials-file:` only when the name is not passed on the command
line — which is why upstream's `service install` demands them.

If the published service advertises a public origin of its own, such as an OAuth
discovery URL, `hostname` has to match that origin. Otherwise clients reach the
tunnel and then fail to authenticate.

## One-time manual steps

Logging in is a browser flow and creating a tunnel is an account call, so neither is
automated. The `cloudflared_tunnel_credentials` target reports what is missing and
fails the push with what to run:

```sh
cloudflared tunnel login
```

Then create the tunnel, route its DNS, and set the variables above in the host
profile.

`~/.cloudflared/cert.pem` and `~/.cloudflared/<uuid>.json` are live-local secrets.
Neither is tracked, and nothing here reads their contents.

## Why a user unit

`cloudflared service install` writes a system unit as root and, unless
`--no-update-service` is passed, also installs a daily timer that runs
`cloudflared update` and restarts the service. Where the system package manager owns
the binary, that timer replaces it behind the manager's back.

The tracked unit runs unprivileged with `--no-autoupdate` instead, and uses
`Type=exec` rather than upstream's `Type=notify`: readiness reporting buys nothing
here, and exec cannot hang waiting for a notification that never arrives.

## Verifying

The standalone renderer exposes only `--var` assignments, not the repo's own
variables, so pass the values explicitly:

```sh
dotman render jinja packages/linux/cloudflared/files/cloudflared/config.yml \
  --var cloudflared.hostname=<host> --var cloudflared.local_service=<origin> > /tmp/tunnel.yml
cloudflared --config /tmp/tunnel.yml tunnel ingress validate
systemctl --user status cloudflared
curl -sS -o /dev/null -w '%{http_code}\n' https://<hostname>/mcp
```

`--config` is a global flag, so it goes before the subcommand. A `401` from the last
command means the tunnel and the service behind it are both up.

## Notes

- A wrong config or missing credentials makes the unit restart every 5s. Check
  `journalctl --user -u cloudflared` rather than assuming a network problem.
- Do not put a Cloudflare Access application in front of the hostname: it terminates
  the request before the published service sees it.

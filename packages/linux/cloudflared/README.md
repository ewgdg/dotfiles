# Cloudflare Tunnel client

Installs `cloudflared`. Nothing else.

A tunnel is a concrete thing: it publishes one hostname and forwards it to one local
service. That unit and its ingress rules therefore live in the package that owns the
published service, next to the code that decides what it publishes — not here, where
they would need variables to stay generic. A second tunnel gets its own package
depending on this one.

## Setting up a tunnel

```sh
cloudflared tunnel login            # writes ~/.cloudflared/cert.pem
cloudflared tunnel create <name>    # writes ~/.cloudflared/<uuid>.json
```

Then route the hostname to that tunnel in the Cloudflare dashboard. Both files come
from interactive or account-level steps no package can perform, so the package that
publishes a service guards its unit on them with `ConditionPathExists` and the unit
skips itself until they exist. Nothing fails; the service simply has no public URL yet.

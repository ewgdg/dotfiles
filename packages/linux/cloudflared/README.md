# Cloudflare Tunnel client

Installs `cloudflared`. Nothing else.

A tunnel is a concrete thing: it publishes one hostname and forwards it to one local
service. That unit and its ingress rules therefore live in the package that owns the
published service, next to the code that decides what it publishes — not here, where
they would need variables to stay generic. A second tunnel gets its own package
depending on this one.

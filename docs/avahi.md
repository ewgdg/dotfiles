# Avahi

`packages/linux/avahi` installs Avahi and constrains `avahi-daemon` to physical LAN interfaces.

The package target keeps a full copy of `/etc/avahi/avahi-daemon.conf` with one added placeholder line after Avahi's commented sample. `packages/linux/avahi/scripts/render_avahi_daemon_conf.py` fills that placeholder instead of storing host interface names in the repo.

Render behavior:

- scans `/sys/class/net`
- keeps interfaces with a physical `device` entry and Ethernet/Wi-Fi link type
- excludes loopback, Docker bridges, veth pairs, and other virtual-only links
- replaces only `__DOTMAN_AVAHI_ALLOWED_INTERFACES__`
- fails if no physical Ethernet/Wi-Fi interface is found, to avoid rendering a broad Avahi config

Capture behavior keeps the repo source machine-independent by restoring the placeholder value:

```ini
allow-interfaces=__DOTMAN_AVAHI_ALLOWED_INTERFACES__
```

`linux/sunshine` depends on this package so Sunshine mDNS advertisement stays on the real LAN only.

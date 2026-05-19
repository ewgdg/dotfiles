# Avahi

`packages/linux/avahi` installs Avahi and constrains `avahi-daemon` to physical LAN interfaces.

## Why this package exists

Avahi publishes the host's `.local` name and services on every interface it considers relevant. On a Docker host, that default can include Docker bridges and veth peers, not just the real LAN.

Bad result:

- `.local` may advertise Docker/private addresses such as `172.17.0.1` or `172.18.0.1`
- IPv6 link-local records may be published on random `veth*` peers
- clients can cache or choose a bad address
- hostname conflict recovery can leave the host renamed, for example `name-2.local`, until Avahi restarts
- Sunshine discovery can show up on the wrong network instead of the physical LAN

The robust fix is an Avahi allow-list of real Ethernet/Wi-Fi interfaces. Interfaces not listed are ignored, so Docker bridges, veth peers, VPNs, and other virtual links are excluded by omission.

## Why render the allow-list

Avahi interface filters are name-based, but Linux interface names differ by machine:

```ini
allow-interfaces=enp7s0,wlan0
```

That is correct for one host but wrong for another. The repo source must stay machine-independent, so the package stores a placeholder:

```ini
allow-interfaces=__DOTMAN_AVAHI_ALLOWED_INTERFACES__
```

`packages/linux/avahi/scripts/render_avahi_daemon_conf.py` fills the placeholder at push/render time from the target host.

### Render behavior

- scans `/sys/class/net`
- excludes loopback
- keeps interfaces with a physical `device` entry and Ethernet/Wi-Fi link type
- excludes Docker bridges, veth pairs, and other virtual-only links because they do not have a backing hardware device there
- replaces only `__DOTMAN_AVAHI_ALLOWED_INTERFACES__`
- fails if no physical Ethernet/Wi-Fi interface is found, to avoid rendering a broad Avahi config

### Capture behavior

Capture restores the placeholder, so capturing `/etc/avahi/avahi-daemon.conf` never commits host-local names.

## Why not other Avahi options

`deny-interfaces=docker0` is insufficient. It only denies the literal interface named `docker0`; it does not deny random Docker links like `br-*` or `veth*`.

Avahi does not support wildcard interface filters. `deny-interfaces=veth*` would match only an interface literally named `veth*`.

`allow-point-to-point=no` is useful but not this fix. It ignores `POINTOPOINT` tunnel-style interfaces such as some VPN/PPP links. Docker bridges and veth peers are `BROADCAST,MULTICAST` links, so they are still eligible unless excluded by `allow-interfaces`.

`disallow-other-stacks=yes` is also not this fix. It prevents other local mDNS stacks from binding UDP/5353, but Chrome and other apps may use mDNS for WebRTC privacy or device discovery. Leave it at Avahi's default unless deliberately choosing Avahi as the only local mDNS stack.

## Relationship to Sunshine

`linux/sunshine` depends on this package so Sunshine mDNS advertisement stays on the real LAN only. Sunshine clients should discover the host through the physical LAN address, not Docker/private/veth addresses.

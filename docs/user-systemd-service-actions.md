# Systemd Service Actions

This repo uses a shared dotdrop action, `ensure-systemd-service-enabled`, backed by
`scripts/ensure_systemd_service_enabled.sh`, for managed units that should come up
automatically after installation.

Current users of this action:

- `system keyd.service`
- `user keyd-application-mapper.service`
- `user niri-session-setup.service`
- `user network-virtual-mic.service`
- `user noctalia-shell.service`
- `user sunshine.service`

Behavior:

- checks the enable state before mutating anything
- reloads the user manager before user-service checks
- delays `sudo -A` for system services until the unit exists and is confirmed disabled
- exits without changes when the unit is already enabled
- skips quietly when the target manager or unit is not reachable
- skips user-service enablement when running from a root context

`niri-wait-for-tray-host.service` remains in the repo as a reference unit, but it is no
longer part of the active Niri profile because `noctalia-shell.service` now owns the tray
readiness behavior.

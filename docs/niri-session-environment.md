# Niri Session Environment Provisioning

Niri's `environment {}` block configures variables for Niri and the processes
Niri spawns, but that block does not automatically provision the user systemd
manager or the dbus activation environment for services started alongside the
compositor.

This repo keeps `packages/niri/files/config/niri/session.env` as the source of
truth for the session-wide environment that Noctalia and desktop autostart
should inherit and mirrors it through `niri-shell.service`.

## How it works

- upstream `niri-session` still starts upstream `niri.service`
- `niri-shell.service` is `WantedBy=niri.service`, `After=niri.service`, and
  `PartOf=niri.service`
- `niri-shell.service` runs `~/.config/niri/bin/import-session-environment.sh`
  before starting Noctalia
- the script sources `~/.config/niri/session.env`
- it extracts every variable defined in that file
- it imports the discovered variables into both:
  - `systemctl --user import-environment`
  - `dbus-update-activation-environment --systemd`
- the same unit starts Noctalia, waits for the tray host, then releases
  `graphical-session.target` and `xdg-desktop-autostart.target`

This keeps session-specific variables local to Niri without duplicating them in
separate user units or making them globally active for KDE sessions.
`cfg/misc.kdl` keeps an empty `environment {}` block as the place for variables
that should remain Niri-local instead of being provisioned session-wide.

## Constraints

- keep `session.env` in shell-compatible `KEY=VALUE` form
- quote values when they contain shell metacharacters such as `;`

## Why this exists

Starting Noctalia before `xdg-desktop-autostart.target` is useful because it
provides the tray host early, but a service started that early can race with
environment provisioning if the variables are only imported later from Niri
autostart hooks. Keeping setup and tray gating inside `niri-shell.service`
avoids that race and removes the Niri-only `noctalia-shell.service`.

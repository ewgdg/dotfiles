# Niri Session Environment Provisioning

Niri's `environment {}` block configures variables for Niri and the processes Niri spawns,
but that block does not automatically provision the user systemd manager or the dbus
activation environment for services started alongside the compositor.

This repo keeps `dotfiles/config/niri/session.env` as the source of truth for the
session-wide environment that Niri user services should inherit and mirrors it through
`niri-session-setup.service`.

## How it works

- `niri-session-setup.service` runs `Before=niri.service` and is `WantedBy=niri.service`
- the service executes `~/.config/niri/bin/import-session-environment.sh`
- the script sources `~/.config/niri/session.env`
- it extracts every variable defined in that file
- it imports the discovered variables into both:
  - `systemctl --user import-environment`
  - `dbus-update-activation-environment --systemd`
- the same unit also runs `/usr/lib/pam_kwallet_init` so early Niri session preparation
  lives in one place

This lets early session services such as Noctalia see the same session-specific variables
without duplicating them in each unit or making them globally active for KDE sessions.
`cfg/misc.kdl` keeps an empty `environment {}` block as the place for variables that should
remain Niri-local instead of being provisioned session-wide.

## Constraints

- keep `session.env` in shell-compatible `KEY=VALUE` form
- quote values when they contain shell metacharacters such as `;`

## Why this exists

Starting Noctalia before `xdg-desktop-autostart.target` is useful because it provides the
tray host early, but a service started that early can race with environment provisioning if
the variables are only imported later from Niri autostart hooks.

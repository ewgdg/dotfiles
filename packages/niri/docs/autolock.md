# Niri Autolock

Niri locking is split by responsibility:

- Noctalia manages normal idle lock/screen-off behavior via its own idle
  settings.
- `cfg/autostart.kdl` locks immediately after greetd autologin when
  `AUTOLOGIN_SESSION=1` is present. `packages/greetd` injects that generic
  marker into `[initial_session].command` during render.

The immediate lock path retries briefly because Noctalia/Quickshell may still be
starting when Niri runs startup commands.

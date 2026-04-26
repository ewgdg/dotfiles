# greetd package

`packages/greetd` replaces the tracked `sddm` package in desktop groups.

## Autologin source of truth

The greetd template does **not** hard-code the autologin command. By default,
`packages/greetd/scripts/render_greetd_config.py` writes a runtime launcher
command using `{{ vars.desktop.session }}`:

```toml
command = "env AUTOLOGIN_SESSION=1 /usr/local/bin/greetd-start-session <session>"
```

`packages/greetd/files/usr/local/bin/greetd-start-session` resolves
`<session>.desktop` at login time from standard session directories, extracts
the `[Desktop Entry]` `Exec=` value, parses the supported session-launcher
subset, and `exec`s it.

This keeps dotman render repo-pure. Desktop entries such as
`/usr/share/wayland-sessions/cosmic.desktop` may be created by another package's
`pre_push` hook in the same `dotman push`, so render must not require them to
already exist.

Profiles can override that lookup with `vars.desktop.session_command`. When this
value exists, `packages/greetd` passes it as `--session-command`, and the render
script writes it directly to `[initial_session].command` without using the
runtime helper. This is useful for compositor-specific wrappers such as Sway
startup flags or session environment setup.

Every rendered initial session is prefixed with `AUTOLOGIN_SESSION=1` so desktop
sessions can distinguish greetd autologin from a user-selected greeter session.
Niri uses this marker to lock immediately after autologin.

The same render step also fills other greetd-specific placeholders such as the
autologin user.

Pull is paired with `packages/greetd/scripts/capture_greetd_config.py`, which
restores any tracked string value that uses the `__PLACEHOLDER_` prefix. This
keeps `dotman pull` from baking live values back into the tracked template.

Why this exists:

- keeps `profiles/de/*.toml` as the session selector source of truth
- avoids duplicating session launch commands in both display-manager config and
  desktop entry files
- follows upstream session wrapper changes automatically, such as Plasma's
  wrapper helpers
- avoids bootstrap ordering failures when session packages are installed by
  dotman hooks during the same push

Search order:

1. `/usr/local/share/wayland-sessions`
2. `/usr/share/wayland-sessions`
3. `/usr/local/share/xsessions`
4. `/usr/share/xsessions`

The shell helper is intentionally limited to trusted session `.desktop` files,
not arbitrary application launchers. It rejects desktop field codes such as `%f`
instead of trying to emulate the full Freedesktop `Exec=` grammar. The package
`guard_push` hook validates the helper against the selected session with a
Python parser before writing the greetd config.

## Service behavior

`greetd` package hooks:

- install `greetd` and `greetd-tuigreet-fork-bin`
- call shared `{{ ENABLE_DISPLAY_MANAGER_SYSTEMD_UNIT }}` helper for
  `greetd.service`

That shared helper enables requested display-manager unit, then disables any
other enabled display-manager unit that advertises
`Alias=display-manager.service` without stopping the currently running display
manager session. This stays generic across login managers such as SDDM or
Plasma Login and is reusable by other display-manager packages.

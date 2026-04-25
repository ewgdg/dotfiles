# greetd package

`packages/greetd` replaces the tracked `sddm` package in desktop groups.

## Autologin source of truth

The greetd template does **not** hard-code the autologin command. By default,
`packages/greetd/scripts/render_greetd_config.py` resolves
`{{ vars.desktop.session }}.desktop` from standard session directories and copies
its `Exec=` line into `[initial_session].command`.

Profiles can override that lookup with `vars.desktop.session_command`. When this
value exists, `packages/greetd` passes it as `--session-command`, and the render
script writes it directly to `[initial_session].command` without requiring a
matching `.desktop` file. This is useful for compositor-specific wrappers such as
Sway startup flags or session environment setup.

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

Search order:

1. `/usr/local/share/wayland-sessions`
2. `/usr/share/wayland-sessions`
3. `/usr/local/share/xsessions`
4. `/usr/share/xsessions`

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

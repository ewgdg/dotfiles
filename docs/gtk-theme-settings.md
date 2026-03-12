# GTK Theme Settings

This repo tracks GTK appearance explicitly instead of relying on session-specific runtime state.

## How GTK theme resolution works

GTK has multiple settings sources, and the active source depends on toolkit version and desktop session.

- GTK 4 on Wayland prefers the desktop-wide settings sharing mechanism first. The official GTK 4 docs describe this as a settings portal. The portal interface is `org.freedesktop.portal.Settings`. If that mechanism is unavailable, GTK 4 falls back to `settings.ini`.
- GTK 3 uses desktop/session settings when available and falls back to `settings.ini` when those are unavailable. The GTK 3 docs explicitly describe X11 `XSettings` plus `settings.ini` fallback; Wayland behavior is less clearly documented in the same level of detail.
- Application-level overrides can still bypass both.

Relevant user config files:

- `~/.config/gtk-3.0/settings.ini`
- `~/.config/gtk-4.0/settings.ini`

Relevant desktop/runtime settings:

- KDE/Qt apps: `~/.config/kdeglobals`
- GSettings/dconf keys such as `org.gnome.desktop.interface icon-theme`
- Portal settings interface: `org.freedesktop.portal.Settings`

## Best practice for dotfiles

Do not back up the raw dconf database.

Reasons:

- It is not a clean declarative config source.
- It contains unrelated desktop state.
- It is difficult to review and maintain.

Preferred approach:

- Track `gtk-3.0/settings.ini`.
- Track `gtk-4.0/settings.ini`.
- Treat `gtk-3.0/settings.ini` as the source of truth for shared theme state that also needs to propagate into session settings.
- Track `gtk.css` and `colors.css` only when they are intentional overrides you want to preserve.
- Track KDE icon/theme settings separately in `kdeglobals` when KDE apps must match.
- If a session depends on GSettings on Wayland, set only the specific keys you care about during setup instead of backing up the whole dconf database.
- Ignore `assets/` and GTK bookmarks unless they are intentionally user-authored customizations.

This gives a readable source of truth while still allowing session-specific integration layers to work.

## Current repo policy

This repo stores GTK settings as text files and uses them as the durable backup format.

Current appearance choices captured from the live system:

- GTK icon theme: `Papirus-Dark`
- GTK theme: `Breeze`
- Cursor theme: `Bibata-Modern-Ice`

## GSettings sync policy

This repo also syncs a small shared subset into GSettings for Wayland session integration.

- `gtk-theme-name` is sourced from `gtk-3.0/settings.ini`
- `gtk-icon-theme-name` is sourced from `gtk-3.0/settings.ini`
- `gtk-cursor-theme-name` is sourced from `gtk-3.0/settings.ini`
- `gtk-cursor-theme-size` is sourced from `gtk-3.0/settings.ini`
- `gtk-application-prefer-dark-theme` is sourced from `gtk-3.0/settings.ini` and mapped to `org.gnome.desktop.interface color-scheme`

The sync script lives at `scripts/sync_gtk_gsettings.py` and is invoked from the `d_config_gtk-3.0` dotdrop entry in `config.yaml`.

## References

- GTK 4 `GtkSettings`: https://docs.gtk.org/gtk4/class.Settings.html
- GTK 3 `GtkSettings`: https://docs.gtk.org/gtk3/class.Settings.html

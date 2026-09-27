# linux/appimage

[AppMan](https://github.com/ivan-hc/AppMan) is the rootless mode of [AM](https://github.com/ivan-hc/AM): a CLI that installs AppImages by name from a 2,500+ app catalog and keeps them updated.

## What this package does

- Downloads the `appman` script to `~/.local/bin/appman`.
- Declines appman's zsh completion, which would append lines to `~/.zshrc`.
- Tracks `~/.config/appman/appman-config`, which sets the apps directory to `~/Applications`.
- Installs `appimageupdatetool` through appman so updates use zsync deltas.
- topgrade's `appman` step runs `appman -u`, which updates apps and appman itself.

## Adding an app

- Add a probe target like `appimageupdatetool_installed`: probe `~/.local/bin/<app>`, install with `appman -i <app>`.
- Some app scripts prompt (for example, to choose a build). Pipe the answer and keep the `[ -x ... ]` check, because appman exits 0 when an install aborts.

## Delta updates

- Deltas only apply when an AppImage embeds update info. Otherwise appman downloads the full file.
- Check an app with `./App.AppImage --appimage-updateinformation`. Empty output means no delta.

## Uninstall residue

- `appman -R <app>` removes the app directory, launcher, desktop entry, and icon.
- It leaves the app's own `~/.config`, `~/.local/share`, and `~/.cache` data.

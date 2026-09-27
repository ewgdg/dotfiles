# linux/appmanager

[AppManager](https://github.com/kem-a/AppManager) is a GTK4 app that installs, integrates, and updates AppImages without root.

## What this package does

- Installs `appmanager` from the AUR.
- Does not track settings or the installed AppImages. Apps live in `~/Applications` and are live state.

## Delta updates

- Updates use zsync deltas only when an AppImage embeds update info. Otherwise it downloads the full file.
- Check an app with `./App.AppImage --appimage-updateinformation`. Empty output means no delta.

## Uninstall residue

- Removing an app deletes the AppImage, desktop entry, and icon, but not its `~/.config`, `~/.local/share`, or `~/.cache` data.
- Use isolated portable mode for trial apps; it keeps `.home` and `.config` beside the AppImage so deleting the app removes everything.

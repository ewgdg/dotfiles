# linux/appimage

[soar](https://github.com/pkgforge/soar) installs AppImages and other portable apps under your home directory, without root, from a declared package list.

## What this package does

- Downloads the soar release binary to `~/.local/bin/soar`.
- Tracks `~/.config/soar/packages.toml` and runs `soar apply --yes` after pushing it.
- topgrade's `soar` step runs `soar sync`, `soar update`, and `soar self update`.
- The shell package puts `~/.local/share/soar/bin` on `PATH`. Desktop entries use absolute paths and don't need it.

## Adding an app

- Find it with `soar search <name>`, then add `<name> = "*"` under `[packages]` and push.
- For apps outside the catalog, use `<name> = { github = "owner/repo", asset_pattern = "*x86_64*.AppImage" }`.
- soar writes resolved versions back for `url` and forge entries; `dotman pull` brings those edits into the repo.
- `soar apply` does not remove apps dropped from the list. Run `soar remove <name>`, or `soar apply --prune` to remove everything unlisted.

## Delta updates

- soar uses zsync when an AppImage embeds an update feed. Otherwise it downloads the full file.
- Check an app with `./App.AppImage --appimage-updateinformation`. Empty output means no delta.

## Uninstall residue

- `soar remove <name>` removes the package, its links, desktop entry, and icon.
- It leaves the app's own `~/.config`, `~/.local/share`, and `~/.cache` data.

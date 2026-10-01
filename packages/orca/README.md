# orca

[Orca](https://github.com/stablyai/orca) runs Claude Code, Codex, OpenCode, and other agents side by side, each in its own git worktree.

## What this package does

- Installs the desktop app upstream ships: the official AppImage on Linux (`x86_64` and `arm64`), the `stablyai/orca/orca` tap cask on macOS.
- On Linux the AppImage lands at `~/Applications/orca.AppImage` with a desktop entry and icons (see `scripts/install_appimage.sh`). Orca's updater replaces that file in place, so dotman only installs it once.
- Does not link a command. Use the app's "Install CLI" action; on Linux it links `~/.local/bin/orca-ide`, named to avoid GNOME Orca's `/usr/bin/orca`.
- Homebrew's core `orca` cask is plotly's Orca, so macOS installs by the tap-qualified name.

## Settings

Orca keeps everything in one file: `~/.config/Orca/profiles/local-default/orca-data.json` (`~/Library/Application Support/Orca/...` on macOS). Preferences, keybindings included, live under `settings`. The rest is app state: repos, worktree metadata, UI layout, sessions, SSH targets, and caches.

- The package syncs `settings`, minus its `not:` paths in `vars.orca.synced_selectors`: secrets and signed-in accounts, machine-specific values, and per-machine history.
- `dotman pull` saves the rest of `settings`. `dotman push` overlays it and keeps every excluded live field.
- New upstream settings sync automatically. Review pulls, and add any new secret or machine-specific field to the exclude list.
- Home paths are stored as `~`.
- Quit Orca before `dotman push`. The app keeps its state in memory and would write over the pushed file.
- The repo file does not exist until the first `dotman pull` after Orca has run.
- Only the default `local-default` profile is tracked. Other profiles get generated IDs.
- Upstream is preparing a SQLite store (`profile-state.db`) in the same folder. If settings move there, this target stops tracking them.

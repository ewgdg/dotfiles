# orca

[Orca](https://github.com/stablyai/orca) runs Claude Code, Codex, OpenCode, and other agents side by side, each in its own git worktree.

## What this package does

- Installs the desktop app upstream ships: the official AppImage on Linux (`x86_64` and `arm64`), the `stablyai/orca/orca` tap cask on macOS.
- On Linux the AppImage lands at `~/Applications/orca.AppImage` with a desktop entry and icons (see `scripts/install_appimage.sh`). Orca's updater replaces that file in place, so dotman only installs it once.
- Does not link a command. Use the app's "Install CLI" action; on Linux it links `~/.local/bin/orca-ide`, named to avoid GNOME Orca's `/usr/bin/orca`.
- Homebrew's core `orca` cask is plotly's Orca, so macOS installs by the tap-qualified name.

## Settings are not tracked

Orca keeps settings under the `settings` key of `~/.config/Orca/profiles/<profileId>/orca-data.json`. That file also holds repos, worktree metadata, UI state, and a GitHub cache, and the profile ID differs per machine. Upstream is also preparing a SQLite store (`profile-state.db`) in the same directory. Some renderer preferences live in Electron Local Storage.

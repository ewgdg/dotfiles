# t3code

[T3 Code](https://t3.codes) is a desktop, web, and mobile control surface for local coding agents (Claude Code, Codex, OpenCode, and others).

## What this package does

- Installs the desktop app: the official x86_64 AppImage on Linux, the `t3-code` cask on macOS.
- On Linux the AppImage lands at `~/Applications/t3code.AppImage` with a desktop entry, icons, and a `~/.local/bin/t3code` link (see `scripts/install_appimage.sh`). The app's updater checks every few minutes and replaces that file in place with delta downloads, so dotman only installs it once.
- Release asset names carry the version and there is no unversioned alias, so `scripts/latest_appimage_url.sh` reads the current file name from the release's `latest-linux.yml`, the manifest the app itself updates from.
- The AUR `t3code-bin` was rejected: it is current, but it unpacks the AppImage into `/opt`, which turns off the in-app updater and remote "Update server" from other clients, leaving updates to whenever pacman runs.
- The standalone `t3` CLI (`curl … | sh` into `~/.local/bin`) is not installed. The desktop app runs its own server; install the CLI only for headless hosts or `t3 app`.

## Tracked config

All under `~/.t3/userdata/` (the `T3CODE_HOME` default):

- `settings.json` — server settings. Stored sparse: only values that differ from defaults. Secrets (provider API keys, tokens) live in `secrets/`, not here.
- `client-settings.json` — device preferences such as appearance and confirmations. Written in full, so pulls include defaults.
- `keybindings.json` — keybinding rules. T3 Code writes its defaults on first start and appends new ones on later starts, so pulls include defaults.

Repo sources start absent; dotman plans no change while both sides are missing. After the app writes a file, capture it with `dotman pull`.

## Not tracked

- `desktop-settings.json` — window bounds, WSL, update channel; mostly machine state.
- `secrets/`, `state.sqlite`, `attachments/`, `logs/`, `environment-id`, `anonymous-id`, `server-runtime.json`, `saved-environments.json`, `themes/`.
- `~/.t3/worktrees` and `~/.t3/caches`.

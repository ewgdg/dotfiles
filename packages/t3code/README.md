# t3code

[T3 Code](https://t3.codes) is a desktop, web, and mobile control surface for local coding agents (Claude Code, Codex, OpenCode, and others).

## What this package does

- Installs the desktop app: `t3code-bin` from the AUR on Linux, the `t3-code` cask on macOS.
- The AUR package is published by upstream's release workflow, so it does not lag releases. It unpacks the AppImage into `/opt`, which leaves the in-app updater inactive; pacman (or topgrade) owns updates.
- The standalone `t3` CLI (`curl … | sh` into `~/.local/bin`) is not installed. The desktop app runs its own server; install the CLI only for headless hosts or `t3 app`.

## Tracked config

All under `~/.t3/userdata/` (the `T3CODE_HOME` default):

- `settings.json` — server settings. Stored sparse: only values that differ from defaults. Secrets (provider API keys, tokens) live in `secrets/`, not here.
- `client-settings.json` — device preferences such as appearance and confirmations. Written in full, so pulls include defaults.
- `keybindings.json` — keybinding rules. T3 Code appends any missing default bindings on startup, so the first pull after launching will grow this file.

The repo seeds are empty (`{}` / `[]`) so the files can be tracked before the app first runs. After changing settings in the app, capture them with `dotman pull`.

## Not tracked

- `desktop-settings.json` — window bounds, WSL, update channel; mostly machine state.
- `secrets/`, `state.sqlite`, `attachments/`, `logs/`, `environment-id`, `anonymous-id`, `server-runtime.json`, `saved-environments.json`, `themes/`.
- `~/.t3/worktrees` and `~/.t3/caches`.

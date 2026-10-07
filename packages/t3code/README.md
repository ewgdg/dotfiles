# t3code

[T3 Code](https://t3.codes) is a desktop, web, and mobile control surface for local coding agents (Claude Code, Codex, OpenCode, and others).

## What this package does

- Installs the desktop app: the official AppImage for the host CPU (`cpu_arch`: x86_64 or arm64) on Linux, the `t3-code` cask on macOS.
- On Linux the AppImage lands at `~/Applications/t3code.AppImage` with a desktop entry, icons, and a `~/.local/bin/t3code` link (see `scripts/install_appimage.sh`). The app's updater checks every few minutes and replaces that file in place with delta downloads, so dotman only installs it once.
- Release asset names carry the version and there is no unversioned alias, so `scripts/latest_appimage_url.sh` reads the current file name from the release's per-arch manifest (`latest-linux.yml` or `latest-linux-arm64.yml`), the manifest the app itself updates from.
- The AUR `t3code-bin` was rejected: it is current, but it unpacks the AppImage into `/opt`, which turns off the in-app updater and remote "Update server" from other clients, leaving updates to whenever pacman runs.
- The standalone `t3` CLI (`curl … | sh` into `~/.local/bin`) is not installed. The desktop app runs its own server; install the CLI only for headless hosts or `t3 app`.

## Tracked config

All under `~/.t3/userdata/` (the `T3CODE_HOME` default):

- `settings.json` — server settings. Stored sparse: only values that differ from defaults. Secrets (provider API keys, tokens) live in `secrets/`, not here. Per-machine keys are filtered out (see `server_settings_selectors`): the legacy-migration marker `projectSettingsFolded`, per-project overrides keyed by locally generated project ids, device onboarding/hosts, and the default and text-generation model picks, which churn with day-to-day model choice.
  - The `dsh` provider instance runs DeepSeek Harness through T3's ACP driver (`acpRegistry`, source `local`) as `dsh --profile acp`. Launch arguments (`commandArgs`) have no field in the settings form, so they live only in this file. Models and credentials come from DSH's home patch (see `deepseek-harness`).
- `client-settings.json` — device preferences such as appearance and confirmations. Written in full, so pulls include defaults. Per-machine state and favorite models are filtered out (see `client_settings_selectors`).
- `keybindings.json` — keybinding rules. T3 Code writes its defaults on first start and appends new ones on later starts, so pulls include defaults.
- `themes/gruvbox-material.json` — Gruvbox Material dark theme, matching the active Ghostty theme (`Gruvbox Material Dark` plus its cursor override). Seeds `canvas` and `accent`, and overrides text, status, and terminal colors; T3 Code derives the rest. Select it under Settings → Appearance.

Repo sources start absent; dotman plans no change while both sides are missing. After the app writes a file, capture it with `dotman pull`.

## Not tracked

- `desktop-settings.json` — window bounds, WSL, update channel; mostly machine state.
- `secrets/`, `state.sqlite`, `attachments/`, `logs/`, `environment-id`, `anonymous-id`, `server-runtime.json`, `saved-environments.json`, other files in `themes/`.
- `~/.t3/worktrees` and `~/.t3/caches`.

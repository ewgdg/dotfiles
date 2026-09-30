# paseo

[Paseo](https://paseo.sh) runs Claude Code, Codex, and OpenCode agents behind one daemon that desktop and mobile clients connect to.

## What this package does

- Installs the desktop app, which upstream recommends: the official AppImage for the host CPU (`cpu_arch`) on Linux (upstream ships x86_64 only), the `paseo` cask on macOS.
- On Linux the AppImage lands at `~/Applications/paseo.AppImage` with a desktop entry, icons, and a `~/.local/bin/paseo` link (see `scripts/install_appimage.sh`). Paseo's own updater replaces that file in place with delta downloads, so dotman only installs it once; you confirm each update in the app.
- AUR builds were rejected: the `.deb` repacks keep an updater that runs `dpkg` behind pacman, and `paseo-bin` lags upstream by days.
- The desktop build bundles a matching `paseo` CLI and starts its own daemon, so there is no separate npm install.
- Tracks `~/.paseo/config.json` only. The rest of `~/.paseo` is daemon identity (`daemon-keypair.json`, `server-id`, `push-tokens.json`, `cli-client-id`), runtime state, and logs.
- The app and `paseo daemon config set` rewrite `config.json`, so capture changes with `dotman pull`. Keep secrets out of it: set a daemon password through `PASEO_PASSWORD`, not the file.

## Settings that touch other managed files

Leave these off unless the change goes through the owning package:

- `enableTerminalAgentHooks` rewrites `~/.claude/settings.json`, `~/.codex/hooks.json`, and adds an OpenCode plugin.
- Installing Paseo skills copies `paseo-*` into `~/.agents/skills`, `~/.claude/skills`, and `~/.codex/skills`, and the daemon re-syncs them on every start.
- The app's "Install CLI" action symlinks into `~/.local/bin` and edits `~/.zshrc`. Not needed: the package already links `paseo` into `~/.local/bin`.

State lives in `PASEO_HOME`, which defaults to `~/.paseo`.

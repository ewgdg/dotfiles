# paseo

[Paseo](https://paseo.sh) runs Claude Code, Codex, and OpenCode agents behind one daemon that desktop and mobile clients connect to.

## What this package does

- Installs the desktop app, which upstream recommends: `paseo-desktop-bin-edge` from the AUR on Arch (official `.deb`, includes betas), the `paseo` cask on macOS.
- The desktop build bundles a matching `paseo` CLI and starts its own daemon, so there is no separate npm install.
- Does not track `~/.paseo` yet. `config.json` sits beside logs, worktrees, and cached auth, so choose what to track after a first run.

## Settings that touch other managed files

Leave these off unless the change goes through the owning package:

- `enableTerminalAgentHooks` rewrites `~/.claude/settings.json`, `~/.codex/hooks.json`, and adds an OpenCode plugin.
- Installing Paseo skills copies `paseo-*` into `~/.agents/skills`, `~/.claude/skills`, and `~/.codex/skills`, and the daemon re-syncs them on every start.
- The app's "Install CLI" action symlinks into `~/.local/bin` and edits `~/.zshrc`. Not needed: the package already puts `paseo` on `PATH`.

State lives in `PASEO_HOME`, which defaults to `~/.paseo`.

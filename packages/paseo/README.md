# paseo

[Paseo](https://paseo.sh) runs Claude Code, Codex, and OpenCode agents behind one daemon that desktop and mobile clients connect to.

## What this package does

- Installs the CLI and daemon from npm (`@getpaseo/cli`), matching upstream's Linux install docs.
- Does not track `~/.paseo` yet. `config.json` sits beside logs, worktrees, and cached auth, so choose what to track after a first run.

## First run

```sh
paseo   # starts the daemon, then offers the E2E relay and a pairing QR code
```

State lives in `PASEO_HOME`, which defaults to `~/.paseo`.

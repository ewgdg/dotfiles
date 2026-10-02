# himalaya

Mail CLI for agents and scripts: [himalaya](https://github.com/pimalaya/himalaya) reaches Gmail and Outlook over IMAP, with OAuth tokens from [ortie](https://github.com/pimalaya/ortie) kept in the Secret Service keyring. The agent-side usage lives in the `email` skill (`packages/agents/files/agents/skills/email/`).

Linux only for now (`groups/apps/linux.toml`): token storage uses `secret-tool`.

## Private addresses

This repo is public, so addresses live in the dotman local override `~/.config/dotman/repos/main/local.toml`:

```toml
[vars.email.gmail]
address = "you@gmail.com"

[vars.email.outlook]
address = "you@outlook.com"
```

Without them the templates fail to render and the push stops.

## First sign-in

After `dotman push`, authorize each account once:

```sh
ortie auth get -a gmail
ortie auth get -a outlook
```

Both finish on their own: the browser returns to ortie's local listener.
Outlook relies on the Thunderbird app accepting the `http://127.0.0.1` loopback, as current Thunderbird does. If Microsoft answers with a redirect URI mismatch, set `endpoints.redirection = "https://localhost"` for Outlook and finish with the `ortie auth resume` command that `auth get` then prints, passing the browser's failed URL.

Check with `himalaya envelope list -a gmail` and `-a outlook`.

## Sending switch

Each account is drafts-only by default. To allow sending, override in `local.toml`:

```toml
[vars.email.outlook]
send = true
```

himalaya gains that account's `smtp` section; without it, `message send` fails. Both tokens always carry send rights (Gmail has no send-free scope, and Outlook's is granted up front), so toggling needs no new sign-in.

Agents with shell access can still use the stored token directly; the switch prevents mistakes, not a determined attacker.

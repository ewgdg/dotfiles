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

Outlook redirects to `https://localhost/...`, which no local server answers, so `auth get` prints an `ortie auth resume --state=... --pkce=... <REDIRECTED_URI>` command instead. Run it with the browser's failed `https://localhost/?code=...` URL, single-quoted. The printed command omits the account, which works because `outlook` is ortie's default account.

Check with `himalaya envelope list -a gmail` and `-a outlook`.

## Sending switch

Each account is drafts-only by default. To allow sending, override in `local.toml`:

```toml
[vars.email.outlook]
send = true
```

- himalaya gains that account's `smtp` section; without it, `message send` fails.
- Outlook's token also gains the `SMTP.Send` scope, so the server enforces drafts-only too. Re-run `ortie auth get -a outlook` after toggling.
- Gmail has no send-free IMAP scope, so for Gmail the missing `smtp` section is the only switch.

Agents with shell access can still use the stored token directly; the switch prevents mistakes, not a determined attacker.

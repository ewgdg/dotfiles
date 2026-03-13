# Niri Post-Startup Auth Prompt Reconciliation

This repo now uses Noctalia's built-in `screenUnlock` hook to reconcile auth prompts after
the lock screen is dismissed:

- `dotfiles/config/niri/bin/move-auth-prompts-to-workspace.sh`
- `dotfiles/config/noctalia/settings.json`

## Purpose

Some auth prompts can appear while Noctalia has the session locked immediately after
startup. When the session is unlocked, these prompts may still be on an unexpected
workspace.

The Noctalia settings hook runs `~/.config/niri/bin/move-auth-prompts-to-workspace.sh
main` on `screenUnlock`, which moves matching KWallet and 1Password prompts onto the
`main` workspace.

## Behavior

- On the first `screenUnlock` of each login session, the mover script scans Niri windows for:
  - `org.kde.ksecretd`
  - `kwallet`
  - `1password`
  - `1password-quickaccess`
- Matching windows are moved to `main`, focused, floated, and centered.
- A marker file in `$XDG_RUNTIME_DIR/noctalia-first-unlock-auth-prompts.done` prevents
  repeated runs within the same session.

## Logs

Use the journal to inspect what happened:

```sh
journalctl --user -t move-auth-prompts -b
```

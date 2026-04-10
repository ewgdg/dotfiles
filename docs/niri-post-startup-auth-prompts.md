# Niri Post-Startup Auth Prompt Reconciliation

The auth-prompt mover script is currently kept in the repo but is not wired into
Noctalia's `screenUnlock` hook:

- `packages/niri/files/config/niri/bin/move-auth-prompts-to-workspace.sh`
- `packages/noctalia/files/config/noctalia/settings.json`

## Current Approach

The auth-prompt startup and refocus experiment has been removed. The repo
currently does not reconcile auth prompts automatically during startup or
unlock.

## Notes

- `move-auth-prompts-to-workspace.sh` is retained for possible future reuse.
- `startup-unlock-kwallet.sh` is retained for possible future reuse.
- Because the unlock hook is disabled, auth prompts are no longer moved after
  the lock screen is dismissed.

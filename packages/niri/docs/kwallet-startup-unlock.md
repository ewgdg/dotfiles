# Niri KWallet Startup Unlock Helper

`packages/niri/files/config/niri/bin/startup-unlock-kwallet.sh` triggers the
KWallet unlock prompt during session startup.

## Behavior

- If a KWallet prompt already exists, the script exits without opening another one.
- Otherwise the script requests `org.kde.KWallet.open(...)` over D-Bus.

## Usage

- Default wallet name:

```sh
~/.config/niri/bin/startup-unlock-kwallet.sh
```

- Custom wallet name and request app id:

```sh
~/.config/niri/bin/startup-unlock-kwallet.sh kdewallet startup-unlocker
```

## Notes

- The helper is currently retained in the repo but is not launched automatically at startup.
- Noctalia's `screenUnlock` hook is currently disabled for auth-prompt reconciliation.
- 1Password is intentionally not triggered here because there is no documented
  "unlock prompt only" CLI mode that avoids opening Quick Access or the main app window.
- Match patterns are heuristic. If KWallet changes the dialog app id or title,
  verify the live values with `niri msg pick-window` and update the jq filters.

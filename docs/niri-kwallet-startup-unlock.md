# Niri KWallet Startup Unlock Helper

`dotfiles/config/niri/bin/startup-unlock-kwallet.sh` triggers the KWallet unlock prompt
during session startup. Workspace placement is handled separately by the Noctalia
`screenUnlock` hook.

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

- Workspace movement is intentionally handled by the Noctalia unlock hook instead of the
  startup helper.
- 1Password is intentionally not triggered here because I did not find a documented
  "unlock prompt only" CLI mode that avoids opening Quick Access or the main app window.
- Match patterns are heuristic. If KWallet changes the dialog app id or title, verify
  the live values with `niri msg pick-window` and update the jq filters.

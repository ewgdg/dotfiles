# Switch Desktop

`dotfiles/bin/switch-desktop` switches the machine between KDE Plasma and Niri without running a full dotdrop apply.

It updates:

- `/etc/sddm.conf.d/zzz-autologin.local.conf`
- `TARGET_USER_HOME/.config/sunshine/sunshine.conf`

Usage:

```sh
switch-desktop kde
switch-desktop niri
switch-desktop status
switch-desktop --user xian kde
ssh -t host sudo switch-desktop niri
```

Notes:

- `kde_settings.conf` remains the tracked SDDM default.
- `/etc/sddm.conf.d/zzz-autologin.local.conf` is generated local state and is ignored by dotdrop compare/update.
- KDE writes `Session=plasma`.
- Niri writes `Session=niri`.
- The script re-executes itself with plain `sudo` when it needs to update the SDDM config.
- It resolves the Sunshine path from the target user's passwd entry instead of the caller's `HOME`, so it works from SSH and `sudo`.
- When the script is run directly as root, it falls back to the current effective user. Pass `--user USERNAME` if you want to target a different account.
- It expects `~/.config/sunshine/sunshine-kde.conf` and `~/.config/sunshine/sunshine-niri.conf` to exist for the target user.

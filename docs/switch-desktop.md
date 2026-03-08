# Switch Desktop

`dotfiles/bin/switch-desktop` switches the machine between KDE Plasma and Niri without running a full dotdrop apply.

It updates:

- `/etc/sddm.conf.d/zzz-autologin.local.conf`
- `~/.config/sunshine/sunshine.conf`

Usage:

```sh
switch-desktop kde
switch-desktop niri
switch-desktop status
```

Notes:

- `kde_settings.conf` remains the tracked SDDM default.
- `/etc/sddm.conf.d/zzz-autologin.local.conf` is generated local state and is ignored by dotdrop compare/update.
- KDE writes `Session=plasma`.
- Niri writes `Session=niri`.
- The script uses `sudo -A` when it needs to update the SDDM config.
- It expects `~/.config/sunshine/sunshine-kde.conf` and `~/.config/sunshine/sunshine-niri.conf` to exist.

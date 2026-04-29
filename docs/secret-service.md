# Secret Service backend

Wayland session portal configs prefer GNOME Keyring as the only Secret portal
backend:

```ini
org.freedesktop.impl.portal.Secret=gnome-keyring;
```

KWallet remains installed for KDE-native wallet use, but its Secret Service
compatibility API is disabled in `kwalletrc` to avoid ambiguous fallback when
Electron/libsecret apps store secrets.

`packages/secret-service` installs `gnome-keyring` and `libsecret` for desktop
groups. `gnome-keyring` does not depend on `libsecret` on Arch:
`gnome-keyring` provides the backend, while `libsecret` provides common client
tooling/libraries such as `secret-tool`.

On Arch, the `gnome-keyring` package install script enables
`gnome-keyring-daemon.socket` globally for user sessions. This repo does not
duplicate that enable step. Do not enable `gnome-keyring-daemon.service` here;
D-Bus/socket activation is enough, and the service can still start on demand.

With greetd autologin, GNOME Keyring cannot be unlocked by PAM at session start
because no login password is entered. Use the normal login password for the
default keyring so PAM unlock works if autologin is later disabled.

# Secret Service backend

Decision: use KWallet again as the Secret Service provider on Linux desktops.
Reason: GNOME Keyring falls back to GTK/GCR dialogs outside GNOME, which looks
out of place and has shown focus/behavior bugs in non-GNOME sessions.

Wayland session portal configs prefer KWallet as the only Secret portal backend:

```ini
org.freedesktop.impl.portal.Secret=kwallet;
```

`packages/secret-service` owns `~/.config/kwalletrc` and enables the KWallet
Secret Service compatibility API:

```ini
[org.freedesktop.secrets]
apiEnabled=true
```

No custom `org.freedesktop.secrets` D-Bus activation file is managed here. The
previous Niri KWallet setup worked by enabling KWallet's Secret Service API and
letting the KWallet portal/session activate `ksecretd` as needed.

`packages/secret-service` installs `kwallet`, `kwalletmanager`, and
`libsecret`. `kwallet` provides `ksecretd`, the KWallet portal backend, and
KWallet's Secret Service compatibility daemon. `libsecret` provides common
client tooling/libraries such as `secret-tool`.

With greetd autologin, KWallet still cannot be unlocked by PAM at session start
because no login password is entered. Keep the wallet password equal to the
normal login password so PAM unlock can work if matching KWallet PAM
integration is installed and autologin is later disabled. For autologin
sessions, expect the first secret access to show the KWallet unlock prompt.

Diagnostics:

```sh
busctl --user status org.freedesktop.secrets
busctl --user list | rg 'secrets|kwallet|ksecret|keyring'
secret-tool store --label=test service test user me
secret-tool lookup service test user me
```

# WayVNC

- Purpose: temporary/control-plane remote access to the active Wayland desktop, mainly to approve portal dialogs such as Sunshine XDG Portal capture.
- Package: `packages/wayvnc`.
- Service: `~/.config/systemd/user/wayvnc.service`.
- Config: `~/.config/wayvnc/config` is local-only because it contains password/auth choices.
- Example config: `~/.config/wayvnc/config.example`.
- Local keys are generated if missing: `tls_key.pem`, `tls_cert.pem`, `rsa_key.pem`.
- Bind: `127.0.0.1:5900` in the generated example/default config. Use an SSH tunnel from the client instead of exposing VNC on LAN.
- Start condition: service only starts when the compositor exposes wlroots screencopy plus virtual pointer/keyboard protocols.

From client:

```bash
ssh -N -L 5900:127.0.0.1:5900 user@host
```

Then connect VNC viewer to:

```text
127.0.0.1:5900
```

Check host:

```bash
systemctl --user status wayvnc --no-pager -l
journalctl --user -u wayvnc -b --no-pager -n 80
```

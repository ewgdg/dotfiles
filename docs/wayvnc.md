# WayVNC

- Purpose: temporary/control-plane remote access to the active Wayland desktop, mainly to approve portal dialogs such as Sunshine XDG Portal capture.
- Package: `packages/wayvnc`.
- Services:
  - `~/.config/systemd/user/wayvnc.service`: raw VNC server on localhost.
  - `~/.config/systemd/user/wayvnc-novnc.service`: noVNC/websockify browser bridge on localhost.
- Config: `~/.config/wayvnc/config` disables WayVNC auth by default because both services bind only to localhost and SSH tunnels are the access boundary.
- Example config: `~/.config/wayvnc/config.example`.
- Local keys are generated if missing: `tls_key.pem`, `tls_cert.pem`, `rsa_key.pem`.
- Bind:
  - raw VNC: `127.0.0.1:5900` in the generated example/default config.
  - browser noVNC: `127.0.0.1:6080`, proxied to raw VNC by `novnc`.
- Use an SSH tunnel from the client instead of exposing VNC/noVNC on LAN. Do not expose this config directly to Ethernet without adding a real auth/TLS layer such as Caddy.
- `wayvnc.service` uses `--render-cursor` so browser clients get an explicit captured cursor.
- Native WayVNC websocket mode (`--websocket`) crashed with current Arch `wayvnc/neatvnc`; use the `novnc` bridge instead.
- Start condition: service only starts when the compositor exposes wlroots screencopy plus virtual pointer/keyboard protocols.

From client:

```bash
ssh -N -L 5900:127.0.0.1:5900 user@host
```

Then connect VNC viewer to:

```text
127.0.0.1:5900
```

For browser/noVNC from Mac:

```bash
ssh -N -L 6080:127.0.0.1:6080 user@host
```

Then open:

```text
http://127.0.0.1:6080/vnc.html
```

Check host:

```bash
systemctl --user status wayvnc wayvnc-novnc --no-pager -l
journalctl --user -u wayvnc -u wayvnc-novnc -b --no-pager -n 120
```

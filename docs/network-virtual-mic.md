# Network Virtual Mic

This setup receives audio from the network, plays it into a dedicated PipeWire null sink, and exposes that sink's monitor as a virtual microphone.

## Host side

Tracked files:

- `~/.config/systemd/user/network-virtual-mic.service`
- `~/bin/network-virtual-mic`

Install or update the dotfiles, then reload user units:

```bash
systemctl --user daemon-reload
systemctl --user enable --now network-virtual-mic.service
```

Select `Network Virtual Mic` as the microphone in apps like Discord, OBS, or browsers.

Useful checks:

```bash
systemctl --user status network-virtual-mic.service
pactl list short sinks | rg network-virtual-mic
pactl list short sources | rg network-virtual-mic
journalctl --user -u network-virtual-mic.service -f
```

## Configure the receiver

Defaults are embedded directly in the user service and listen for MPEG-TS over UDP port `55041`.

Current unit environment:

```dotenv
NVM_INPUT_URL=udp://0.0.0.0:55041?listen=1
NVM_INPUT_FORMAT=mpegts
```

You can point `ffmpeg` at any input URL it supports. Common examples:

```dotenv
NVM_INPUT_URL=http://0.0.0.0:8080/live.mp3
NVM_INPUT_FORMAT=
```

```dotenv
NVM_INPUT_URL=rtsp://camera-or-sender/live
NVM_INPUT_FORMAT=
```

After editing the user service:

```bash
systemctl --user daemon-reload
systemctl --user restart network-virtual-mic.service
```

## Sender examples

Send Pulse/PipeWire monitor audio from another Linux machine over UDP MPEG-TS:

```bash
ffmpeg -re \
  -f pulse -i default \
  -ac 2 -ar 48000 \
  -c:a mp2 -b:a 192k \
  -f mpegts udp://HOST_IP:55041
```

Send an existing audio file for testing:

```bash
ffmpeg -re -stream_loop -1 -i sample.wav \
  -ac 2 -ar 48000 \
  -c:a mp2 -b:a 192k \
  -f mpegts udp://HOST_IP:55041
```

## Notes

- This is plain network audio. Use it on a trusted LAN or over a VPN.
- The service only removes the sink and source modules if it created them. If you pre-create those names elsewhere, they are left alone.

# linux/xembedsniproxy

XEmbed → StatusNotifierItem proxy for Wayland. The Dotman package keeps the
functional `xembedsniproxy` family name and installs the locally maintained
`xembed-sni-proxy` executable. The distinct executable name avoids colliding
with Plasma's `/usr/bin/xembedsniproxy`.

Bridges legacy X11, Wine, and Proton system-tray icons into StatusNotifierItem
hosts such as Noctalia and waybar under niri, Hyprland, and sway.

## Layout

The Python project uses a standard `src/` package:

```text
src/xembed_sni_proxy/
├── __init__.py
└── bridge.py
```

`uv tool install --editable` installs the `xembed-sni-proxy` console script.
The editable install resolves the repository source directly, so source changes
apply when the process next starts and the dotfiles checkout must remain at the
recorded location.

## Managed helper window

The proxy uses a managed utility window with `WM_CLASS=xembed-sni-proxy`.
The niri rule matches `app-id=^xembed-sni-proxy$` and keeps this required X11
tray-owner window hidden on the stash workspace without focusing it.

## Runtime

- Runs as `xembedsniproxy.service`, bound to `graphical-session.target`.
  Plasma's separate unit is `plasma-xembedsniproxy.service`; the unit names do
  not conflict. The implementations must not run simultaneously because only
  one process can own `_NET_SYSTEM_TRAY_S0`.
- IconPixmap defaults to `--byte-order network`, the SNI specification's
  A,R,G,B byte order used by Noctalia, waybar, Quickshell, and KDE.
- Python dependencies (`python-xlib`, `dbus-python`, and `PyGObject`) come from
  PyPI. A first build needs the normal compiler, pkg-config, DBus,
  GObject-introspection, Cairo, and Python headers.

## Upstream provenance

The implementation started from
[`waliori/wine-sni-bridge`](https://github.com/waliori/wine-sni-bridge) commit
`676c5dd2b932`. It is now maintained as a fork with additional behavior:

- alpha-aware extraction, chroma keying, cropping, and bounded retries;
- map/unmap → Active/Passive state without premature undocking;
- deterministic X11 background repainting;
- SaveSet protection and clean XEmbed release across proxy restarts;
- suppression of Wine's standalone fallback tray after icons re-dock;
- unique SNI object paths for multiple icons from one process;
- conservative application-title inference from matching X11 icons;
- clean selection contention and supervised tray-window restart behavior.

Review upstream changes separately and port applicable changes into
`src/xembed_sni_proxy/bridge.py`; do not overwrite the maintained
implementation wholesale.

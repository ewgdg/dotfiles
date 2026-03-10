# Steam Wayland IME Workaround

`dotfiles/local/share/applications/steam.desktop` overrides the stock Steam launcher
to start Steam with:

```desktop
Exec=env XMODIFIERS=@im=fcitx GTK_IM_MODULE=xim /usr/bin/steam %U
```

This is a workaround for Steam's current Wayland IME/input handling. On this
machine, Steam does not reliably accept Chinese input from the stock launcher
even when `XMODIFIERS=@im=fcitx` is already present in the session environment.

Keep this override only as long as it is needed. Once Steam's native Wayland
text input works reliably, remove the extra launcher environment overrides and
drop the local `steam.desktop` override entirely.

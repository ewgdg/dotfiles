# LinearMouse

LinearMouse stores settings in two places:

- `~/Library/Preferences/com.lujjjh.LinearMouse.plist` — app/general preferences.
- `~/.config/linearmouse/linearmouse.json` — device/profile settings such as scroll distance/mode, pointer tuning, and button behavior.

The JSON file is the important target for scroll mode changes like **By Pixels**.

This package keeps the JSON device-agnostic by matching only device categories (`mouse` / `trackpad`). Do not commit generated per-device identifiers such as serial numbers, vendor IDs, or product IDs unless a setting really must differ per physical device.

## Scrolling on macOS

Use LinearMouse scroll mode **By Pixels** for terminal apps on macOS.

Reason: **By Lines** can be interpreted differently by terminal emulators, because the terminal still converts wheel input into terminal rows and may apply its own scroll multiplier. This can make a LinearMouse setting like “x lines” scroll farther than expected.

Known terminal-side multipliers/defaults:

```conf
# Kitty low-precision wheel path
wheel_scroll_multiplier 5.0

# Kitty high-precision/pixel path
touch_scroll_multiplier 1.0
pixel_scroll yes
```

```toml
# Alacritty
[scrolling]
multiplier = 3
```

With **By Pixels**, macOS/LinearMouse sends pixel/precision-style scrolling, which avoids line-count double-scaling and tends to feel consistent across Kitty and Alacritty.

No terminal config override is needed unless scrolling still feels too fast or slow.

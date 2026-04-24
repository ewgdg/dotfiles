---
name: privileged-commands
description: >
  Use only when plain sudo may fail because normal prompting is unavailable.
  Decide which fallback approach is appropriate.
---

Use this skill only for edge cases where normal `sudo` may not work.

## Rule

- Default: if root is needed and normal interactive prompting works, use plain `sudo`.
- If no controlling terminal is available and `SUDO_ASKPASS` points to an executable helper, use plain `sudo`; sudo will invoke askpass automatically.
- If a controlling terminal exists but the password owner cannot interact with that terminal prompt, use `sudo -A` to force askpass.

## Notes

- Verify askpass before relying on it: prefer an explicit `SUDO_ASKPASS` program that exists and is executable.
- Do not treat `[ -t 0 ]` alone as “no tty”; sudo may still use the process controlling terminal (for example, this can happen inside TUI/agent harnesses where the user cannot answer that prompt).
- If `SUDO_ASKPASS` is not set, sudo may still use an askpass path configured in `sudo.conf`; check before adding extra fallback logic.
- If no askpass helper is configured but a graphical prompt is acceptable, and a tool like `zenity` exists, it is acceptable to create a small temporary askpass helper around it.
- Do not leak this agent-only fallback logic into normal user-facing docs, hooks, or command examples.

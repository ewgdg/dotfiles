---
name: privileged-commands
description: >
  Use only when plain sudo may fail because normal prompting is unavailable.
  Decide which fallback approach is appropriate.
---

Use this skill only for edge cases where normal `sudo` may not work.

## Rule

- Default: if root is needed and normal interactive prompting works, use plain `sudo`.
- If no reliable tty prompt is available, consider `sudo -A` only after confirming an askpass helper is available and appropriate for the session.

## Notes

- `sudo -A` is not default. Use it only when `sudo` cannot reliably prompt on a terminal.
- Before choosing `sudo -A`, verify askpass is usable. Prefer an explicit `SUDO_ASKPASS` program that exists and is executable.
- If no askpass helper is already configured but a graphical prompt is acceptable, and a tool like `zenity` exists, it is acceptable to create a small temporary askpass helper around it.
- Do not leak this agent-only fallback logic into normal user-facing docs, hooks, or command examples.

---
name: privileged-commands
description: >
  Use only when plain sudo may fail because normal prompting is unavailable.
  Decide which fallback approach is appropriate.
---

Use this skill only for edge cases where normal `sudo` may not work.

`agent-sudo COMMAND [ARG...]` runs the real command with `sudo -A`, forcing
askpass instead of terminal prompting. Use it when sudo may prompt somewhere the
password owner cannot answer, such as inside an agent/TUI harness.

## Rule

- Use plain `sudo` when normal interactive prompting works.
- Use `agent-sudo` when the prompt may be unreachable.

## Notes

- Let sudo decide policy for the actual command; avoid preflight checks.

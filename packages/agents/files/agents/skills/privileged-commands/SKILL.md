---
name: privileged-commands
description: >
  Use only when plain sudo may fail because normal prompting is unavailable.
  Decide which fallback approach is appropriate.
---

Use this skill only when normal `sudo` prompting may be unreachable, such as
inside an agent/TUI harness.

Prefer plain `sudo` when interactive prompting works. Otherwise run the
skill-local helper:

```sh
{baseDir}/scripts/agent-sudo COMMAND [ARG...]
```

`{baseDir}` is the directory containing this `SKILL.md`. Resolve it to an
absolute path; do not assume `agent-sudo` is on `$PATH`.

The helper runs the command with `sudo -A`, forcing askpass instead of terminal
prompting. Let sudo decide policy for the actual command; avoid preflight checks.

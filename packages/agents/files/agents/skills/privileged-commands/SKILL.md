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
./scripts/agent-sudo --reason REASON [--] COMMAND [ARG...]
```

Path is relative to the skill root; run it from there or resolve it first. Do not assume `agent-sudo` is on `$PATH`.

The helper runs the command with `sudo -A`, forcing askpass instead of terminal
prompting. Let sudo decide policy for the actual command; avoid preflight checks.

Always pass a short, concrete reason when invoking the helper so the password
popup tells the human why elevation is needed:

```sh
./scripts/agent-sudo --reason "Install build dependency required by tests" apt install -y shellcheck
```

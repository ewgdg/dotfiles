---
name: privileged-commands
description: >
  Use only when plain sudo may fail because normal prompting is unavailable.
  Decide which fallback approach is appropriate.
---

Use this skill only when normal `sudo` prompting may be unreachable, such as
inside an agent/TUI harness.

Prefer plain `sudo` when interactive prompting works.

If `sudo` works but terminal prompting may be unreachable, run the skill-local helper:

```sh
./scripts/agent-sudo --reason REASON [--] COMMAND [ARG...]
```

Path is relative to the skill root; run it from there or resolve it first. Do not assume `agent-sudo` is on `$PATH`.

The helper runs the command with `sudo -A`, forcing askpass instead of terminal
prompting. Let sudo decide policy for the actual command; avoid preflight checks.

Use `pkexec` only as a secondary fallback when `sudo`/askpass is unsuitable and a
polkit authentication agent is available, usually in a desktop session. Prefer
full program paths and simple argv commands:

```sh
pkexec --disable-internal-agent --keep-cwd /usr/bin/apt install -y shellcheck
```

`--disable-internal-agent` prevents pkexec from falling back to an unreachable
text prompt inside an agent/TUI. `pkexec` sanitizes the environment and may
change working directory without `--keep-cwd`; do not expect shell aliases,
PATH, redirection, or GUI environment variables to survive. Use `sh -c` only
when truly needed, and quote deliberately.

Always pass a short, concrete reason when invoking the helper so the password
popup tells the human why elevation is needed:

```sh
./scripts/agent-sudo --reason "Install build dependency required by tests" apt install -y shellcheck
```

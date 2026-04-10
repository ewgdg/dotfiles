## RTK - Rust Token Killer (Codex CLI)

**Usage**: Token-optimized wrapper for external shell commands.

### Rule

Use `rtk` by default for external commands.

For shell builtins or compound shell syntax, run a shell through `rtk` instead of treating the builtin as a standalone executable.

Examples:

```bash
rtk rg -n "TODO|FIXME" src
rtk git status
rtk cargo test
rtk npm run build
rtk pytest -q
rtk sh -lc 'cd /tmp && pwd'
rtk sh -lc 'printf "a\nb\n" | wc -l'
```

### Meta Commands

```bash
rtk gain            # Token savings analytics
rtk gain --history  # Recent command savings history
rtk proxy <cmd>     # Run raw command without filtering, but still track usage
```

### Exceptions

- Do not write invalid forms such as `rtk cd /tmp`; `cd` is a shell builtin, not an external command.
- When a command needs pipes, redirection, command substitution, or multiple shell steps, prefer `rtk sh -lc '...'`.
- Use `rtk proxy <cmd>` only when you need unfiltered raw output or when RTK filtering would interfere with the task.

### Verification

```bash
rtk which rtk
rtk --version
rtk gain
rtk sh -lc 'command -v rtk'
```

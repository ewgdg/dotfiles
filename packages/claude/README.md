# Claude Code

Managed Claude Code configuration, helpers, and status-line renderers. Domain terms live in `CONTEXT.md`.

## Permissions

- `EnterPlanMode` is denied so Claude never switches into plan mode on its own; planning follows the ExecPlan workflow instead. Enter plan mode manually with Shift+Tab when wanted.
- `ExitPlanMode` stays allowed: it is how Claude presents a plan for approval and leaves plan mode. Denying it traps a manually started plan-mode session.

## Copy

- Fullscreen TUI copy-on-select is off (`copyOnSelect` in `~/.claude.json`); copy explicitly instead.
- `keybindings.json` binds `ctrl+insert` to `selection:copy`, matching the keyd copy chord (`C-insert`). Ghostty's `performable:ctrl+insert` passes the key through when Ghostty itself has no selection.

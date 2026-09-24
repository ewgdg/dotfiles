# Claude Code

Managed Claude Code configuration, helpers, and status-line renderers. Domain terms live in `CONTEXT.md`.

## Permissions

- `EnterPlanMode` is denied so Claude never switches into plan mode on its own; planning follows the ExecPlan workflow instead. Enter plan mode manually with Shift+Tab when wanted.
- `ExitPlanMode` stays allowed: it is how Claude presents a plan for approval and leaves plan mode. Denying it traps a manually started plan-mode session.

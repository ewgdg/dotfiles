---
name: delegation-orchestrator
description: Use when the parent agent should act as controller and decision-maker, delegating research, planning, implementation, review, and validation to available subagents. Trigger for loop mode, orchestration mode, delegate-first workflows, review/fix loops, or user requests to keep the main thread as supervisor only.
---

# Delegation Orchestrator

## Activation and Scope

Use for loop mode, orchestration mode, supervisor-only mode, delegate-first work, and review/fix loops.

Infer scope from the user's activation wording:

- Task-scoped: `start <mode> loop`, `run <mode> loop`, `begin <mode> loop`, or `<mode> loop for <task>` means use this mode for the requested task only. Exit automatically when the task reaches its stop condition.
- Session-scoped: `activate <mode> mode`, `enable <mode> mode`, `turn on <mode> mode`, or `<mode> mode on` means keep this mode active until the user explicitly says it is off or should exit, e.g. `<mode> off` or `<mode> exit`.
- Ambiguous activation: default to task-scoped when tied to a concrete task, and session-scoped when phrased as a persistent mode toggle.

## Core Rules

Parent = controller and decision-maker. Subagents = labor and advice.

The parent may inspect context as needed for delegation, synthesis, and final acceptance. The parent should not become the main labor path for implementation, broad exploration, or large manual fixes.

Use the available delegation backend. If backend mechanics matter, read that backend's docs/skill instead of guessing.

Define acceptance and stop rules before implementation work.

Keep one writer in a shared worktree. Parallelize only read-only labor unless writers are isolated.

Parent owns tradeoffs. Children may recommend, but unapproved scope/product/architecture/safety decisions must escalate.

Parent synthesizes child results; do not forward child output as final judgment.

Review/fix loops stop at the first good stopping point: acceptance met, remaining feedback is optional/out of scope, or user-given loop cap reached.

When this mode is active, do not spawn subagents for simple answer-only requests unless delegation adds real value or the user explicitly asks.

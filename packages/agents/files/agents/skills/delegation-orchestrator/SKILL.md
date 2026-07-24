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

## Core Rules

Parent = controller and decision-maker. Subagents = labor and advice.

Parent may carry some light work after deciding they are too small to delegate. Parent may directly answer user query if no extra work is needed.

The parent may inspect only enough context for delegation, synthesis, and final acceptance. The parent must not perform broad research or large file inspection directly; delegate those to subagents. The parent should not become the main labor path for implementation, broad exploration, or non-trivial manual fixes.

Use the available delegation backend. If backend mechanics matter, read that backend's docs/skill instead of guessing.

Keep one writer in a shared worktree. Parallelize only read-only labor unless writers are isolated.

Prefer one focused task per delegate over bundling unrelated tasks into one worker. When work units are independent, schedule multiple delegates concurrently; if any concurrent delegate may edit files, use isolated worktrees when possible.

Prefer fresh context for each delegated task so the child receives only task-relevant context. Use forked context only when parent conversation history is necessary for the task.

Parent owns tradeoffs. Children may recommend, but unapproved scope/product/architecture/safety decisions must escalate.

Parent synthesizes child results; do not forward child output as final judgment.

Review/fix loops stop at the first good stopping point: acceptance met, remaining feedback is optional/out of scope, or user-given loop cap reached.

## Thinking Level

Choose the right level of thinking level that is just sufficient for the delegated task. Higher thinking is not automatically better; it costs more, slows work, and can produce over-analysis when the task mainly needs faithful execution.

Parent decides thinking level from task role, ambiguity, instruction detail, task length, and harm profile.

### Default Heuristic

- `low`: repetitive, extractive, or mechanical work where correctness comes from following explicit inputs, not inventing judgment.
- `medium`: bounded analysis or implementation with some local choices, but clear acceptance criteria and enough context.
- `high` or `xhigh`: broad review, ambiguous debugging, architecture/product/security decisions, problem solving, innovations, long horizon tasks where instructions cannot cover every edge, analysis or final synthesis/judgment.

Break long tasks into smaller tasks before raising thinking. If a task remains broad after decomposition, use higher thinking because the delegate must fill gaps responsibly.

Smaller/simpler tasks should generally use lower thinking levels. More detailed instructions or an exec plan usually lowers required thinking; missing details, unclear tradeoffs, or high-stakes consequences raise it.

### Role Guidance

- Reviewer: usually `high` for thorough scans. False positives are cheaper than missed bugs. Ask for evidence, severity, and exact locations; parent filters noise.
- Implementation from detailed exec plan: usually `low` or `medium`. The delegate should follow the plan, keep code simple, and avoid re-litigating settled design.
- Summarizing large context: `low`. Treat as robotic extraction/compression. Ask for structured info, source paths, and uncertainty markers, not deep interpretation.
- Planning or decomposing a vague request: `high` or `xhigh`, then delegate resulting small tasks at lower levels.
- Validation commands, log triage, inventory, grep/file map: `low`.
- Security, data loss, privacy, migration, public API, or irreversible decisions: `high` or `xhigh`.
- Puzzle solving or novel idea reasoning/researching: `xhigh`

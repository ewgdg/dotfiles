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

## Cost-Saving Mode

Enable only when the user explicitly asks for cost-saving, cheap-agent, budget, low-cost, or similar delegation behavior.

Use cheap agents for trivial, bounded, low-reasoning tasks: narrow search, file inventory, command output summaries, simple validation, or exact implementation instructions.

Do not use cheap agents for synthesis, final decisions, architecture/product/security tradeoffs, ambiguous debugging, complex refactors, or high-stakes work.

If cheap-agent output is uncertain, weak, or failing validation, escalate to a stronger agent.

### Cheap Models

- DeepSeek latest flash model with high thinking
- OpenAI Codex latest GPT mini model with high thinking
- OpenAI Codex latest GPT model with low thinking

## Core Rules

Parent = controller and decision-maker. Subagents = labor and advice.

Parent may carry some light work after deciding they are too small to delegate. Parent may directly answer user query if no extra work is needed.

The parent may inspect only enough context for delegation, synthesis, and final acceptance. The parent must not perform broad research or large file inspection directly; delegate those to subagents. The parent should not become the main labor path for implementation, broad exploration, or non-trivial manual fixes.

Use the available delegation backend. If backend mechanics matter, read that backend's docs/skill instead of guessing.

Keep one writer in a shared worktree. Parallelize only read-only labor unless writers are isolated.

Prefer one focused task per delegate over bundling unrelated tasks into one worker. When work units are independent, schedule multiple delegates concurrently; if any concurrent delegate may edit files, use isolated worktrees when possible.

Parent owns tradeoffs. Children may recommend, but unapproved scope/product/architecture/safety decisions must escalate.

Parent synthesizes child results; do not forward child output as final judgment.

Review/fix loops stop at the first good stopping point: acceptance met, remaining feedback is optional/out of scope, or user-given loop cap reached.

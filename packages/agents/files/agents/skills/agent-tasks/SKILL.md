---
name: agent-tasks
description: >
  Subtasks for autonomous agent orchestration, kept as TaskNotes on the Agent Board in the user's Obsidian vault. Use when an orchestration session splits work into subtasks, picks the next ready subtask, or a worker starts or finishes one. Work done together with the user (grilling, wayfinder, design sessions) goes to GitHub issues instead.
---

# Agent Tasks

A **subtask** is one TaskNote owned by agents (`owner: agent`), with **blockers** that must be `done` before it is **ready**. Subtasks live on their own Agent Board, apart from the user's tasks; the vault picks up new files live, so Obsidian need not be running.

Always go through the helper; it writes the frontmatter TaskNotes expects and edits only the lines it changes:

```bash
~/.agents/skills/agent-tasks/run.py --help
```

## Roles

**Planner** (the orchestration session with the user): split the work into subtasks, one `create` per subtask, wiring `--blocked-by` so the order is explicit.

```bash
~/.agents/skills/agent-tasks/run.py create --title "<title>" --blocked-by <task stem> <<'EOF'
## Brief
<what to do, where, and the context a fresh agent needs>

## Done when
<checkable criteria>
EOF
```

Add `--parent <task stem>` to nest it under another task, the user's or an agent's.

`create` prints the new task path; its file stem is the task id for `--blocked-by`, `claim`, and `finish`.

**Dispatcher**: the only role that claims. List ready subtasks, claim each one before handing it to a worker thread:

```bash
~/.agents/skills/agent-tasks/run.py ready
~/.agents/skills/agent-tasks/run.py claim <task stem> --thread <thread id>
```

**Worker**: the brief in the task note is the whole assignment. New work discovered mid-task becomes a new `create` with blockers, left for the dispatcher. On finishing, record the **result**: what changed, the PR URL if any, and what remains open.

```bash
~/.agents/skills/agent-tasks/run.py finish <task stem> [--outcome failed] <<'EOF'
<result>
EOF
```

`--outcome failed` parks the subtask as `paused`: its dependents stay blocked until the planner re-plans.

## Reading

Read and search subtasks with normal file tools under `run.py print-path`; filter on `owner: agent`.

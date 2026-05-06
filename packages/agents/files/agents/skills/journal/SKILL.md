---
name: journal
description: >
  Backup Obsidian journaling skill for agents without the global `journal_write` Pi extension tool. Use after agent work when there is meaningful delta with future review value, such as meaningful progress, a reusable lesson or insight, a corrected assumption, a consequential decision, a workflow improvement, a resolved blocker, a useful idea or reframe, or a surprise that changes understanding or direction. Write automatically when criteria pass.
---

# Journal Backup

Use this skill only when the `journal_write` tool is unavailable.

Agent-triggered: decide after meaningful work. If criteria pass, write one journal entry automatically. If not, do nothing.

## Signal filter

Skip trivial activity, routine updates, implementation noise, obvious facts, and low-signal thoughts.

Avoid self-referential journal noise. Log skill/workflow changes only when the change itself has future review value.

## Entry shape

Create:

- `Highlight`: short concrete proposition; say what changed, no vague titles like "Update" or "Progress".
- `Journal`: concise, information-dense reflection capturing the event, what changed, and why it may matter.

Use `$caveman` style compacted language. Optimize for future review. No padding. Prefer 1-4 tight sentences or compact bullets.

## Author

Helper sets frontmatter `author` automatically.

Best-effort format:

1. `agent-<harness>-<provider>-<model>`
2. `agent-<harness>-<model>`
3. `agent-<harness>`
4. `agent`

Use the most complete form available. Never guess provider or model. For pi with no exposed provider/model, use `agent-pi`.

## Write

Run:

```bash
~/.agents/skills/journal/run.sh "<Highlight>" "<Journal>"
```

Optional author override:

```bash
~/.agents/skills/journal/run.sh "<Highlight>" "<Journal>" "agent-pi-provider-model"
```

QuickAdd owns note creation and the vault's journal-day boundary. The helper only passes `Highlight`/`Journal` and post-sets `author`.

---
name: journal
description: >
  Create and search Obsidian journal entries; use the journal directory as a searchable memory store when agents need prior context. Use after agent work when there is meaningful delta with future review value; create automatically before final response when criteria pass, without waiting for the user to ask. Triggers include meaningful progress, a mistake made and corrected, a reusable lesson or insight, a corrected assumption, the user challenging or re-correcting the agent, a consequential decision, a workflow improvement, a resolved blocker, a useful idea or reframe, a surprise that changes understanding or direction, debugging with 3+ back-and-forth turns that resolves a concrete cause, source/docs/code inspection revealing non-obvious external tool behavior, or a reusable project policy/workflow decision.
---

# Journal

Agent-triggered: decide after meaningful work. If criteria pass, create one journal entry automatically. If not, do nothing.

## Journal directory

Discover current journal filesystem directory with the helper:

```bash
journal_dir="$(~/.agents/skills/journal/run.sh print-path)"
```

`print-path` asks Obsidian CLI for the vault base path, then appends `JOURNAL_VAULT_RELATIVE_DIR` (default: `Streams/Journals`). If Obsidian path discovery fails, it falls back to `$HOME/projects/knowledgebase/<journal-relative-dir>`.

For memory recall/search, use normal file tools such as `rg`/`read` against `journal_dir`; do not create a new journal entry for recall.

Example:

```bash
journal_dir="$(~/.agents/skills/journal/run.sh print-path)"
rg "cache|journal_create|commitId" "$journal_dir"
```

## Signal filter

Skip trivial activity, routine updates, implementation noise, obvious facts, and low-signal thoughts.

Avoid self-referential journal noise. Log skill/workflow changes only when the change itself has future review value.

Create at most one journal entry for one meaningful outcome. If you already created one and later need to refine it, edit the returned path with normal file tools; do not create a second entry.

## Entry shape

Create:

- `Highlight`: short concrete proposition; say what changed, no vague titles like "Update" or "Progress". QuickAdd stores this as the note's first alias.
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

## Create

Run the helper with journal body on stdin. No positional body argument exists.

```bash
~/.agents/skills/journal/run.sh create --highlight "<Highlight>" <<'EOF'
<Journal>
EOF
```

Optional author override:

```bash
~/.agents/skills/journal/run.sh create --highlight "<Highlight>" --author "agent-pi-provider-model" <<'EOF'
<Journal>
EOF
```

QuickAdd owns note creation and the vault's journal-day boundary. The helper prints the created path so later refinement can use normal read/edit tools.

Path return rule: `create` prints only the created journal filename, e.g. `2026-...md`. Resolve it against `$(run.sh print-path)` for normal file tools.

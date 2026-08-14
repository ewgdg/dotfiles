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
- `Importance`: number 1-3 for review value. Decimals allowed for fine-tuning exceptional cases. Default is 1 because most entries are routine; choose higher deliberately.
- `Journal`: concise, information-dense reflection capturing the event, what changed, and why it may matter.

Importance scale:

- `3` = must revisit; changed principle, workflow, identity, or future decisions
- `2` = useful review; reusable lesson, insight, or meaningful context
- `1` = routine/searchable memory; default for normal logs and captures

Decimals are allowed only when useful, e.g. `2.5` for stronger-than-normal review value without making it must-revisit.

Metadata safety: `Highlight`, `Importance`, and `Author` become frontmatter `aliases`, `importance`, and `author`. Use the helper instead of hand-writing journal files; it YAML-quotes string metadata before QuickAdd substitution so YAML-significant characters remain safe. Obsidian may later normalize safe quoted scalars back to unquoted YAML; that is OK if frontmatter still parses.

Journal entries must be atomic: each entry is a complete memory unit whose essential meaning is preserved inline. Include key result, numbers, decisions, relevant context, and any takeaway directly in the entry. Do not rely on temporary files, scratch directories, local-only paths, external session artifacts, or "see file X" references for essential meaning. References are allowed only to durable notes/files inside the vault, or when a path itself is the durable subject of the memory. Never use external paths as storage for unstated context.

Use concise language. Optimize for future review.

## Author

Pass `--author` explicitly; the helper does not detect it. The Agent Journal template writes it into the note during creation.

Format: `agent-<harness>-<model>-<reasoning>`

- `<harness>`: the agent harness (`pi`, `codex`, `claude`, ...)
- `<model>`: model id without provider prefix (`deepseek-v4-pro`, not `deepseek/deepseek-v4-pro`)
- `<reasoning>`: the current reasoning level (`high`, `medium`, ...)

Never guess; omit unknown parts rather than invent them. Example: `agent-pi-deepseek-v4-pro-high`.

## Create

Run the helper with journal body on stdin. No positional body argument exists.

```bash
~/.agents/skills/journal/run.sh create --highlight "<Highlight>" --importance 2 --author "agent-pi-deepseek-v4-pro-high" <<'EOF'
<Journal>
EOF
```

QuickAdd's non-opening `Agent Journal` choice owns note creation and the vault's journal-day boundary. Its dedicated template writes agent metadata during creation. The helper validates `--importance` as a number from 1 to 3, defaults to `1`, then prints the created path so later refinement can use normal file tools.

Path return rule: `create` prints the full absolute path of the created journal file.

---
name: context-efficient-navigation
description: Use token-efficient codebase/log navigation workflows. Load when inspecting large repos, logs, generated files, unfamiliar code, structural relationships, or any task where broad file reads would waste context.
---

# Context-Efficient Navigation

Use this skill when accuracy needs targeted evidence, but full-file reads or broad dumps would waste context.

## Core Rule

Save tokens without skipping needed verification. Prefer narrow, evidence-first inspection.

## Search-First Workflow

1. Start with targeted discovery:
   - `rg --files`
   - `rg "literal text"`
   - `find`, `fd`, `ls`, `tree` when useful
2. Read only relevant slices:
   - `sed -n 'START,ENDp' file`
   - `head`, `tail`
   - `wc -l`
3. Expand only when needed:
   - nearby lines
   - callers/callees
   - adjacent modules
   - tests covering same behavior

## Logs and Generated Artifacts

Large or fast-changing files need narrowing first.

Prefer:

- `rg "ERROR|WARN|panic|Traceback" log`
- `tail -n 200 log`
- `head -n 80 log`
- `sed -n 'START,ENDp' log`
- `ls -lh` to spot huge files
- `wc -l` to estimate read cost

Avoid dumping whole logs, lockfiles, generated bundles, snapshots, coverage reports, or minified files unless the whole artifact is genuinely needed.

## Structural Code Questions

Use structure-aware tools before generic text search when asking about:

- callers / callees
- call chains
- inheritance
- overrides
- symbol ownership
- module dependencies
- dead-code triage
- complexity hotspots

Prefer `cgc` for these if available. Load/use the `codegraphcontext-cli` skill for exact commands and caveats.

Use direct text search first for:

- exact strings
- small unambiguous matches
- simple literal lookups
- cases where `cgc` is unavailable or too noisy

## Large Retrieval Tasks

When answer depends on finding a few relevant sections among many candidates:

- prefer available indexing/search workflows
- use `context-mode` only when its MCP tools are configured (`ctx_index`, `ctx_search`, `ctx_fetch_and_index`, etc.)
- do not assume `context-mode` has standalone CLI search/index commands
- avoid repeated broad reads
- extract bounded candidate snippets first
- then reason from those snippets

## Delegation

When a large body of text needs triage or summarization, delegate a bounded extraction/summarization task to a lightweight sub-agent if it reduces main context and does not block critical reasoning.

## Response Discipline

When reporting findings:

- cite exact file paths and line ranges when possible
- summarize only relevant evidence
- mention search commands if they materially affect confidence
- state uncertainty when evidence is partial

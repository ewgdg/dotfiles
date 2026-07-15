---
name: context-efficient-navigation
description: Use token-efficient codebase/log navigation workflows. Load when inspecting large repos, logs, generated files, unfamiliar code, structural relationships, or any task where broad file reads would waste context.
---

# Context-Efficient Navigation

Use this skill when accuracy needs targeted evidence, but full-file reads or broad dumps would waste context.

## Core Rule

Save tokens without skipping needed verification. Prefer narrow, evidence-first inspection.

## Search-First Workflow

Apply when answer depends on finding a few relevant sections among many candidates or large chunks.

Large or fast-changing files need narrowing first.

Avoid dumping whole logs, lockfiles, generated bundles, snapshots, coverage reports, or minified files unless the whole artifact is genuinely needed.

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

## Delegation

When a large body of text needs triage or summarization, delegate a bounded extraction/summarization task to a lightweight, low-cost sub-agent if it reduces main context and does not block critical reasoning. Prefer agents/models configured with low thinking effort for extraction-only work; reserve high-cost reasoning for synthesis or decisions.

## Response Discipline

When reporting findings:

- cite exact file paths and line ranges when possible
- summarize only relevant evidence
- mention search commands if they materially affect confidence
- state uncertainty when evidence is partial

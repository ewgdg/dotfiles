---
name: anti-ai-writing-style
description: Make prose less identifiable as AI-written by grounding claims in real context, uneven human reasoning, verifiable specifics, and author-owned stakes. Use when drafting, rewriting, reviewing, or removing generic LLM tells from posts, notes, essays, comments, and social media.
metadata:
  version: 0.1
  short-description: Avoid AI-coded prose tells
  audience: Writing and editing
  scope: Style, structure, credibility, and authenticity
---

# Anti-AI Writing Style

Name is mnemonic, not ideology. Target is AI-coded prose: generic, synthetic, unaccountable writing that reads like LLM output.

Use this skill when prose risks sounding AI-written: too polished, too balanced, too template-shaped, too generic, or too synthetic-specific.

Goal: make writing feel authored, situated, and accountable. Not by adding typos or fake mess, but by restoring real context, motive, constraints, and uneven human judgment.

## Core Rule

Do not merely make text casual. LLMs can imitate casual. Instead, make text **accountable to a real situation**.

Prefer:

- concrete context over abstract framing
- actual artifacts over vibes
- owned judgment over fake neutrality
- messy sequence over perfect case-study arc
- specific uncertainty over generic caveats
- author motive over audience manipulation

## Common AI-Written Tells To Remove

### 1. Template-shaped argument

AI smell:

Hook → context → comparison → insight → caveat → call-to-action.

Fix:

Let structure follow the real thinking path. Start where the author actually noticed the thing. Preserve digressions if they carry evidence or motive. Cut performative symmetry.

### 2. Synthetic specificity

AI smell:

Precise numbers with no receipts: `4,200 lines`, `17 files`, `3 prompts`, `5-line fix`, `4x better`.

Fix:

Either show the artifact or soften the number.

Use:

- file names
- error messages
- command output
- screenshots
- code snippets
- commit links
- exact prompt excerpts
- what failed first

If no receipt exists, say so. Do not launder vibes through fake precision.

### 3. Credibility pre-padding

AI smell:

`not sponsored`, `real production code`, `I am not an expert`, `nothing exotic`, `actual use case` placed before any evidence.

Fix:

Earn credibility after facts. Mention constraints only when they change interpretation.

Bad:

`This was a real production bug, not a benchmark.`

Better:

`The failing test was in our billing import path, so I cared less about elegance and more about whether the model noticed the retry lifecycle.`

### 4. Fake balance

AI smell:

Over-neat caveats that make promotional writing look neutral: `all models are good`, `not saying X is bad`, `benchmarks miss something important`.

Fix:

State actual preference and actual boundary.

Use:

`For this kind of bug, I would reach for X first. For greenfield code, I still do not know.`

### 5. Generic technical abstraction

AI smell:

`architectural awareness`, `deep reasoning`, `async lifecycle pitfalls`, `production-grade`, `codebase understanding` with no local detail.

Fix:

Attach abstraction to observed behavior.

Bad:

`It had better architectural awareness.`

Better:

`It noticed the cleanup function ran before the second retry finished. The other two kept patching the null check.`

### 6. Smooth paragraph cadence

AI smell:

Every paragraph is similar length, equally polished, and rhetorically complete.

Fix:

Vary rhythm naturally. Some short fragments are fine. Some long sentences can carry thought. Avoid making every paragraph land like a LinkedIn post.

### 7. Engagement-bait ending

AI smell:

`Curious what others think`, `Has anyone else noticed this?`, `Would love data from the community` after a polished persuasive post.

Fix:

Ask only if there is a real missing piece. Make the ask narrow.

Better:

`If someone has tried Qwen on retry/state bugs specifically, I want to see the transcript. General benchmark scores are not useful for this question.`

### 8. Casual veneer over robotic skeleton

AI smell:

Lowercase, slang, or typos placed on top of a perfect marketing/case-study structure.

Fix:

Do not rely on surface casualness. Change the skeleton: more real sequence, more constraints, more decisions, fewer universal claims.

## Rewrite Procedure

1. Identify claim being made.
2. Ask: what would prove or falsify this claim?
3. Add artifact, example, or constraint if available.
4. Remove numbers that cannot be checked.
5. Replace broad praise with observed behavior.
6. Replace fake neutrality with actual boundary.
7. Break template flow if it feels too neat.
8. Cut CTA unless the author needs a specific answer.

## Evidence Ladder

Prefer higher-rung evidence.

1. direct artifact: code, diff, prompt, output, log, screenshot
2. concrete event: when, where, what failed, what changed
3. observed behavior: what the tool/person did differently
4. interpretation: why that difference mattered
5. broad claim: only after enough lower-rung support

Do not start at rung 5.

## Humanizing Without Faking

Good human signals:

- real motive: why author cared
- real constraint: time, context, cost, risk
- real uncertainty: exact thing not known
- real preference: what author would do next
- real artifact: something inspectable
- real sequence: what happened first, second, then after

Bad human signals:

- fake typos
- random lowercase
- forced slang
- performative vulnerability
- invented numbers
- invented skepticism

## Before / After Pattern

AI-coded:

`I tested three models on a real production bug. Model A showed much better architectural awareness and solved it in three messages. This made me realize benchmarks do not capture codebase reasoning.`

Less AI-coded:

`I ran the models against a retry bug in our import worker. The important clue was not another null check. Cleanup was running before the second retry finished. Two models missed that and kept patching guards. DeepSeek pointed at the lifecycle first. That is the difference I care about, not the benchmark score.`

This version is not trying to be prettier. It is more accountable: specific failure, observed model behavior, and narrower claim.

## Review Checklist

Flag text if it has:

- polished case-study arc
- precise but unverifiable numbers
- trust-building disclaimer before evidence
- generic technical praise
- balanced caveat that protects a promotional claim
- repeated paragraph rhythm
- broad conclusion from one anecdote
- CTA that exists only to drive engagement
- casual wording but corporate skeleton

Fix by adding receipts, narrowing claims, showing sequence, and owning the author viewpoint.

## Default Editing Bias

When in doubt:

- narrower claim
- more artifact
- less polish
- less symmetry
- fewer abstractions
- more author stake
- stronger boundary conditions
- no fake numbers
- no fake neutrality

---
name: pseudocode-first
description: Opt-in mode where pseudocode is the human-reviewable source for programming-language behavior changes, and implementation code is compiled from it. Activates only by explicit user request and remains active until stopped. Excludes config, docs, data, markup, styles, lockfiles, generated files, and other non-source artifacts unless explicitly included.
---

# Pseudocode First

Pseudocode is the human-reviewable source of truth. Implementation code is the compiled artifact.

## Activation and Scope

- Activate or adopt only on explicit user request, such as `use pseudocode-first`, `pseudo first`, `pseudocode adopt`, `pseudocode init`, or `pseudocode backfill`.
- Stay active until the user explicitly says to stop pseudocode-first mode.
- Apply only to programming-language source files, such as `.ts`, `.tsx`, `.js`, `.py`, `.rs`, `.go`, `.java`, or `.cpp`.
- Exclude config, docs, data, markup, stylesheets, lockfiles, generated files, and other non-source artifacts unless the user explicitly includes them.

## Core Rule

Before modifying in-scope source code while this mode is active:

1. Find the mapped pseudocode artifact for each affected source file.
2. If mapped pseudocode exists, update it first.
3. If no mapped pseudocode exists, create a pseudocode change proposal first.
4. Compile pseudocode into matching implementation code.

No behavior may be added, removed, or changed in source code unless the pseudocode reflects that behavior first.

## Adopt Command

When user asks for pseudocode adopt, init, or backfill:

1. Find repository root.
2. Discover in-scope source files.
3. Create `pseudocode/` if missing.
4. Create missing canonical mapped pseudocode files.
5. Summarize existing behavior only; do not invent intent or change source code.
6. Mark unclear behavior with `## Review Needed`.
7. Report created, skipped, and review-needed files.

Default discovery:

- Prefer source roots such as `src/`, `lib/`, `app/`, `packages/*/src/`, and language-standard source dirs.
- Skip generated, vendored, build, dependency, fixture, snapshot, minified, and declaration files.
- Include tests only when user explicitly asks or when repo source root is clearly test-only.

Adopt is idempotent: existing mapped pseudocode files are verified and skipped unless user asks for refresh/overwrite.

For large repositories, adopt in batches and ask before generating many files at once. Prefer a dry-run inventory first when scope is unclear.

## Artifact Location

Use a root-level `pseudocode/` directory.

### Canonical mapped pseudocode

Mirror the source path from the repository root:

```text
src/auth/session.ts
=> pseudocode/src/auth/session.ts.pseudo.md

packages/api/src/users.ts
=> pseudocode/packages/api/src/users.ts.pseudo.md
```

Mapped pseudocode is long-lived. Use it for stable module behavior and contracts.

### Change proposals

Use this path when canonical mapped pseudocode is missing:

```text
pseudocode/changes/YYYY-MM-DD-<task-slug>.pseudo.md
```

Change proposals are long-lived, human-reviewable source artifacts for code changes. Do not also create mapped pseudocode unless requested or already present for the changed behavior.

## Pseudocode Granularity

Default to behavior-level pseudocode, not line-by-line code shadowing.
Use declarative, contract-like pseudocode where possible, but prefer clear `if`/`return` behavior over artificial wording.

Primary goal: pseudocode must be clearer than implementation and useful for human review, not template completion.

Include when useful:

- user-visible or module-visible behavior
- state that changes behavior
- important invariants
- errors and failure modes that affect behavior
- side effects that matter to callers/users

Skip unless behavior depends on them:

- private helper names
- local variables
- loop mechanics
- exact library calls
- private data structures
- incidental implementation layout

Document data shapes only at API boundaries, persistence boundaries, module boundaries, or when invariants matter.

Good:

```pseudo
get_current_user(token):
  if token is missing:
    return anonymous
  if session is expired:
    reject session
  return session user
```

Too implementation-shaped:

```pseudo
create sessions_by_id map
loop through session_rows
push each row into result array
call parseDate on expires_at
```

## Artifact Format

Use the smallest artifact that explains the behavior clearly.

Required:

- title
- intent, one short sentence or paragraph
- behavior pseudocode
- `affects` frontmatter in change proposals

For multi-file change proposals, add `Applies to:` near behavior blocks only when needed to disambiguate source mapping.

Add extra sections only when they add real information not already expressed by the behavior pseudocode.

For change proposals, show changed behavior directly. Use `before:`/`after:` or a small `diff` block only when contrast helps review.

Use this default template for mapped pseudocode:

````md
# <Module or Behavior Name>

## Intent

<Why this behavior exists.>

## Behavior

```pseudo
<behavior pseudocode>
```
````

Use this default template for change proposals:

````md
---
affects:
  - path/to/source-file.ext
---

# <Change Name>

## Intent

<Why this change exists.>

## Behavior

```pseudo
<new or changed behavior>
```
````

## Review Gate

Pause before code edits when pseudocode changes behavior in a non-trivial or risky way, or when the user asks to review first.

For small mechanical fixes, you may continue after drafting pseudocode unless the user requested review.

## Compile Rules

Implementation must match pseudocode. If implementation needs to differ, update pseudocode first. Prefer behavior tests derived from pseudocode.

---
name: pseudocode-first
description: Opt-in pseudocode workflow for programming-language source changes. Activates only by explicit user request and remains active until explicitly stopped. Excludes config, docs, data, markup, styles, lockfiles, generated files, and other non-source artifacts unless explicitly included.
---

# Pseudocode First

Pseudocode is the human-reviewable source of truth. Implementation code is the compiled artifact.

## Activation and Scope

- Activate only when the user explicitly asks for pseudocode-first mode, such as `use pseudocode-first`, `pseudo first`, or `/skill:pseudocode-first`.
- Stay active until the user explicitly says to stop pseudocode-first mode.
- Apply only to programming-language source files, such as `.ts`, `.tsx`, `.js`, `.py`, `.rs`, `.go`, `.java`, or `.cpp`.
- Exclude config, docs, data, markup, stylesheets, lockfiles, generated files, and other non-source artifacts unless the user explicitly includes them.

## Core Rule

Before modifying in-scope source code while this mode is active:

1. Find the mapped pseudocode artifact for each affected source file.
2. If mapped pseudocode exists, update it first.
3. If no mapped pseudocode exists, create a pseudocode change proposal first.
4. Compile pseudocode into implementation code.
5. Verify implementation matches pseudocode.

No behavior may be added, removed, or changed in source code unless the pseudocode reflects that behavior first.

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

If no mapped pseudocode exists, create a change proposal:

```text
pseudocode/changes/YYYY-MM-DD-<task-slug>.pseudo.md
```

Use change proposals for unmapped work, cross-cutting changes, migrations, refactors, and draft behavior before deciding where canonical pseudocode belongs.

After compile, if the behavior is long-lived, create or update mapped pseudocode too.

## Status Values

Each pseudocode artifact should have one status:

- `draft` — proposed, not reviewed
- `approved` — user accepted it
- `compiled` — implementation code was changed from it
- `verified` — tests/checks passed and code matches it
- `superseded` — replaced by newer pseudocode

## Pseudocode Granularity

Default to behavior-level pseudocode, not line-by-line code shadowing.

Include:

- user-visible or module-visible behavior
- inputs and outputs at boundaries
- state that affects behavior
- important invariants
- errors and failure modes
- side effects
- acceptance checks

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

## Required Sections

Use this template for mapped pseudocode:

````md
---
status: draft
owns:
  - path/to/source-file.ext
tests:
  - path/to/test-file.ext
---

# <Module or Behavior Name>

## Intent

<One short paragraph explaining why this behavior exists.>

## Behavior

```pseudo
when <condition>:
  do <observable action>
  if <edge case>:
    return <result>
```

## Contracts

- Inputs:
- Outputs:
- Errors:
- Side effects:
- Invariants:

## Acceptance Checks

- [ ] <important case>
- [ ] <edge case>
- [ ] existing behavior preserved

## Compile Map

- `<source-file>` implements `<behavior>`
- `<test-file>` verifies `<acceptance check>`

## Open Questions

- None
````

Use this template for change proposals:

````md
---
status: draft
affects:
  - path/to/source-file.ext
---

# <Change Name>

## Intent

<Why this change is needed.>

## Current Behavior

```pseudo
<current behavior, only if relevant>
```

## Desired Behavior

```pseudo
<new behavior>
```

## Contracts

- Inputs:
- Outputs:
- Errors:
- Side effects:
- Invariants:

## Acceptance Checks

- [ ] <case proving new behavior>
- [ ] <case proving edge behavior>
- [ ] existing behavior preserved

## Compile Plan

- update `<source-file>`
- update/add `<test-file>`

## Open Questions

- None
````

## Review Gate

Pause for user review before code edits when any of these are true:

- behavior is non-trivial
- security, auth, money, data loss, concurrency, or migration involved
- public API changes
- multiple files/modules affected
- user explicitly asks to review pseudocode first

Ask:

```text
Pseudocode drafted at <path>. Say "compile" to implement.
```

For small mechanical fixes, you may continue after drafting pseudocode unless the user requested review.

## Compile Rules

When compiling pseudocode into code:

1. Keep implementation behavior aligned with pseudocode.
2. If implementation needs to deviate, update pseudocode first.
3. Prefer tests that check acceptance criteria, not private implementation details.
4. Update pseudocode status after each phase:
   - `draft` before review
   - `approved` after user approval
   - `compiled` after source edits
   - `verified` after checks pass

## Verification

After implementation, run relevant checks such as tests, lint, typecheck, or targeted scripts.

Then report:

```text
Pseudocode: <path>
Compiled files:
- <source-file>
- <test-file>
Status: verified | compiled-not-verified
Checks: <commands run>
```

If checks fail, keep status `compiled`, report the failure, and do not claim verification.

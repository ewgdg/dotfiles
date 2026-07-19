---
name: dev-writing
description: Create a developer-facing draft when the user or another skill explicitly requires one before posting, such as a pull request, issue, comment, bug report, feature request, or review.
---

# Dev Writing

Use this skill only when the user or another skill explicitly requires a publishable draft before posting developer-facing repository content.

## Rules

- Always generate a draft before posting or submitting anything.
- Store draft files under `<tmp>/drafts/<slug>/`.
- Use a short readable `<slug>` for filesystem use: lowercase, spaces to `-`, remove unsafe chars. It does not need to match the issue/PR title.
- Store internal metadata in `<tmp>/drafts/<slug>/meta.yaml`.
- Store publishable markdown body in `<tmp>/drafts/<slug>/body.md`.
- `body.md` must contain only text safe to post publicly. No internal YAML frontmatter, hidden metadata, planning notes, or agent instructions.
- If the repo does not belong to the user, do not post/create/update PRs or issues until user explicitly approves the draft.
- Use concise style: compressed, direct, no filler, technical substance preserved.
- Use `$personal-writing-style` to mimic user tone.
- Avoid generated-text smell: no polished filler, no generic praise, no boilerplate transitions, no over-explaining, no symmetric essay structure.
- Prefer concrete repo-specific facts, exact files/functions/errors, and direct ask/next step.
- Preserve natural roughness when appropriate: short fragments, plain wording, user-like phrasing.
- First paragraph is the main body, usually a summary.
- Do not add a heading/header before the first paragraph.

## Draft Format

Create two files:

`meta.yaml`

```yaml
title: Real issue or PR title here
type: issue | pr | comment | bug | feature | review | note
repo: owner/name
body_file: body.md
```

`body.md`

```markdown
Main summary paragraph here. No header before this paragraph. This is the first paragraph.

Optional extra details, only if needed. Keep short. Use bullets over sections when enough.

<details>
<summary>Details</summary>

Hide noisy logs, long examples, investigation notes, or extra evidence here.

</details>
```

Keep `body.md` concise and directly publishable. Do not add fixed sections like Context or Changes unless user/repo template needs them. Omit Testing and Risks/Follow-up unless they add real value. Hide noisy details in `<details>` blocks.

## GitHub Notes

- Preserve repo templates when creating issues.
- If template conflicts with this format, preserve template first, but keep first meaningful body paragraph headerless when possible.

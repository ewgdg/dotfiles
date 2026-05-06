---
name: oss-writing
description: Use when writing Git/GitHub/GitLab pull requests, issues, comments, bug reports, feature requests, review summaries, and implementation notes. Always draft before posting.
---

# OSS Writing

Use this skill for OSS-facing PRs, issues, comments, bug reports, feature requests, review summaries, and repo-facing implementation notes.

## Hard Rules

- Always generate a draft before posting or submitting anything.
- Store draft at `/tmp/drafts/<slug>.md`.
- Use a short readable `<slug>` for filesystem use: lowercase, spaces to `-`, remove unsafe chars. It does not need to match the issue/PR title.
- Store real issue/PR title in YAML frontmatter as `title`.
- Do not post/create/update PRs or issues until user explicitly approves the draft.
- Use `$caveman full` style: compressed, direct, no filler, technical substance preserved.
- Use `$personal-writing-style` to mimic user tone.
- Avoid generated-text smell: no polished filler, no generic praise, no boilerplate transitions, no over-explaining, no symmetric essay structure.
- Prefer concrete repo-specific facts, exact files/functions/errors, and direct ask/next step.
- Preserve natural roughness when appropriate: short fragments, plain wording, user-like phrasing.
- First paragraph is the main body, usually a summary.
- Do not add a heading/header before the first paragraph.

## Draft Format

```markdown
---
title: Real issue or PR title here
type: issue | pr | comment | bug | feature | review | note
repo: owner/name
---

Main summary paragraph here. No header before this paragraph. This is the first non-frontmatter paragraph.

Optional extra details, only if needed. Keep short. Use bullets over sections when enough.

<details>
<summary>Details</summary>

Hide noisy logs, long examples, investigation notes, or extra evidence here.

</details>
```

Keep draft concise. Do not add fixed sections like Context or Changes unless user/repo template needs them. Omit Testing and Risks/Follow-up unless they add real value. Hide noisy details in `<details>` blocks.

## Workflow

1. Gather target: PR, issue, or comment, repo, title/thread context, intent, audience, and any template requirements.
2. Write draft to `/tmp/drafts/<slug>.md` with title in frontmatter.
3. Show draft path, frontmatter title, and concise preview.
4. Ask user for approval or edits.
5. Only after approval, post/create/update using frontmatter `title` plus markdown body.

## GitHub Notes

- For GitHub issues, also use `gh-issue-template-create` if available.
- Preserve repo templates when creating issues.
- If template conflicts with this format, preserve template first, but keep first meaningful body paragraph headerless when possible.

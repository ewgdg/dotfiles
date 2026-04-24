---
name: gh-issue-template-create
description: Create GitHub issues from repository issue templates using `gh` while preserving template-owned metadata such as labels and title prefixes.
---

# GitHub Issue Creation From Templates

Use this skill when a repository already has an issue template and the issue must be created through that template path so template-owned metadata is preserved.

## Ground Rules

- Prefer the real template flow over reconstructing the issue manually.
- If labels or title prefixes must come from the template, do not rely on post-creation repair.
- Do not use `gh issue create -T <template> --body ...` or `--body-file ...`; `gh` rejects those combinations.
- Do not rely on `gh issue create -T <template> --title ...` when the template title prefix matters.
- `gh issue create -T <template> --editor` requires a PTY. Run it in TTY mode even when `GH_EDITOR` is scripted.

## Default Agent Workflow

1. Inspect the target repository and confirm the matching issue template exists.
2. If the template controls labels, assignees, or title prefix, use `gh issue create -T "<template>" --editor`.
3. For token-efficient autonomous execution, write the final issue body to a temporary file and use the bundled scripted editor with `GH_EDITOR`.
4. Create the issue in a PTY.
5. Parse the created issue URL or number.

## Preferred Command Pattern

The script path is relative; you may need to run from the skill root:

```bash
GH_ISSUE_TITLE='[Prefix] Final title' \
GH_ISSUE_BODY_FILE=/tmp/issue-body.md \
GH_EDITOR=./scripts/gh_template_editor.sh \
gh issue create -R <owner>/<repo> -T "<template>" --editor
```

## Script Contract

`scripts/gh_template_editor.sh` expects:

- `GH_ISSUE_TITLE`
  The exact final title line to write into the draft.
- `GH_ISSUE_BODY_FILE`
  Path to a markdown body file. If omitted, the script keeps the existing template body and only replaces the first line.

The script preserves any `>8` scissors block that `gh` appends.

## Failure Handling

- If `gh` says `--editor` is unsupported in non-TTY mode, rerun with PTY enabled.
- If the issue is created without expected labels, stop and inspect the repository template configuration before retrying.
- If no matching template exists, fall back to explicit `gh issue create --title ... --body-file ...` and state that template-owned metadata cannot be relied on.

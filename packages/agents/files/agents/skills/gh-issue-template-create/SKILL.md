---
name: gh-issue-template-create
description: Use whenever creating GitHub issues with `gh`; matching repository issue templates are mandatory and must be preserved through safe template-aware flows.
---

# GitHub Issue Creation

Use this skill whenever creating GitHub issues. If a matching repository issue template exists, it must be used. Goal: preserve template-owned metadata such as labels, assignees, title prefixes, and issue-form structure instead of reconstructing issues by hand.

## Hard Rules

- Inspect templates before creating an issue unless user explicitly provides a repository with no templates.
- Prefer the real template flow over reconstructing the issue manually.
- If labels, assignees, or title prefixes come from the template, do not rely on post-creation repair.
- Do not use `gh issue create -T <template> --body ...` or `--body-file ...`; `gh` rejects those combinations.
- Do not rely on `gh issue create -T <template> --title ...` when the template title prefix matters.
- `gh issue create -T <template> --editor` requires a PTY. Run it in TTY mode even when `GH_EDITOR` is scripted.
- If no matching template exists, state that clearly, then use explicit `gh issue create --title ... --body-file ...`.
- If template metadata is expected but missing after creation, stop and inspect template config before retrying.

## Required Inputs

- Repository: current repo or `-R <owner>/<repo>`.
- Issue intent: bug, feature, task, docs, question, etc.
- Final title. Respect template title prefix if present.
- Final body content. Keep template sections unless replacing placeholders is clearly better.
- Labels/assignees/projects only when user requests them or no template owns them.

## Workflow

1. Confirm target repo.
   ```bash
   gh repo view --json nameWithOwner --jq .nameWithOwner
   ```

2. Discover templates.
   ```bash
   scripts/list_issue_templates.sh [-R <owner>/<repo>]
   ```

   Manual fallback:
   ```bash
   find .github/ISSUE_TEMPLATE -maxdepth 1 -type f \
     \( -name '*.md' -o -name '*.yml' -o -name '*.yaml' \) -print
   gh api repos/<owner>/<repo>/contents/.github/ISSUE_TEMPLATE \
     --jq '.[] | select(.type=="file") | .name'
   ```

3. Choose best matching template.
   - Use frontmatter/name/description/about/title/labels as evidence.
   - If `config.yml` disables blank issues and nothing matches, ask user instead of forcing wrong template.
   - If no templates exist, skip to fallback creation.

4. Draft issue body in `/tmp` or `$XDG_RUNTIME_DIR`.

5. Create issue.
   - Template path: use `-T "<template-file>" --editor` with scripted editor and PTY.
   - No-template path: use explicit title/body file.

6. Verify result.
   ```bash
   gh issue view <url-or-number> -R <owner>/<repo> --json title,labels,assignees,url
   ```

## Template-Preserving Command Pattern

Run from the skill root. Use a PTY.

```bash
GH_ISSUE_TITLE='[Prefix] Final title' \
GH_ISSUE_BODY_FILE=/tmp/issue-body.md \
GH_EDITOR=./scripts/gh_template_editor.sh \
gh issue create -R <owner>/<repo> -T "<template>" --editor
```

Capture URL from stdout. Then verify labels/assignees if template should apply them.

## No-Template Fallback Pattern

Use this only after template discovery says no matching template exists.

```bash
gh issue create -R <owner>/<repo> \
  --title 'Final title' \
  --body-file /tmp/issue-body.md
```

Add explicit `--label`, `--assignee`, `--project`, or `--milestone` only when user requested them or repo has no template metadata for the chosen issue type.

## Script Contract

`scripts/gh_template_editor.sh` expects:

- `GH_ISSUE_TITLE`
  The exact final title line to write into the draft.
- `GH_ISSUE_BODY_FILE`
  Path to a markdown body file. If omitted, the script keeps the existing template body and only replaces the first line.
- `GH_ISSUE_BODY`
  Inline markdown body. Lower precedence than `GH_ISSUE_BODY_FILE`. Useful for small issues.

The script preserves any `>8` scissors block that `gh` appends.

`scripts/list_issue_templates.sh` lists local or remote issue templates and extracts common metadata without requiring Python packages.

## Issue Forms Notes

- YAML issue forms (`*.yml`, `*.yaml`) often carry `name`, `description`, `title`, `labels`, `assignees`, and required fields.
- Preserve their sections as much as possible. Do not collapse a required form into an unstructured note unless no CLI-compatible path works.
- If a web-only form cannot be faithfully created by `gh`, use `gh issue create --web -T <template>` when user can complete browser flow; otherwise disclose limitation before fallback.

## Failure Handling

- If `gh` says `--editor` is unsupported in non-TTY mode, rerun with PTY enabled.
- If `gh` rejects `-T` combined with body/title flags, switch to the editor pattern above.
- If the issue is created without expected labels, stop and inspect the repository template configuration before retrying.
- If `gh api` returns 404 for `.github/ISSUE_TEMPLATE`, check current repo and organization-level `.github` defaults before falling back.
- If auth/project scope fails, create issue first only if project assignment is not mandatory; otherwise run `gh auth refresh -s project` or ask user.

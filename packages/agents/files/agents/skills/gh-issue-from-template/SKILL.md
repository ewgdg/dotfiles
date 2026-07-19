---
name: gh-issue-from-template
description: Use when creating a GitHub issue in a repository not owned by the user; discover and preserve matching templates through the correct CLI or web flow.
---

# GitHub Issue Creation

Use this skill only for repositories not owned by the user. Use the repository's matching issue template and preserve template-owned title prefixes, labels, assignees, projects, issue types, and required fields instead of reconstructing them manually. Use `dev-writing` to create the required draft, then obtain approval before posting.

## Workflow

1. Confirm the repository.
   ```bash
   gh repo view --json nameWithOwner --jq .nameWithOwner
   ```

2. Discover repository template files.
   ```bash
   scripts/list_issue_templates.sh [-R <owner>/<repo>] [--json]
   ```

   The helper reads the current checkout without `-R`; with `-R`, it fetches `.github/ISSUE_TEMPLATE` through the REST Contents API. This raw-file discovery sees both Markdown templates and YAML issue forms. It is broader than `gh issue create -T` support.

3. Choose the best match using its `name`, `description`/`about`, title prefix, and metadata. Then branch by extension:

   | Match | Creation flow |
   |---|---|
   | Markdown (`.md`) | `gh issue create -T ... --editor` |
   | YAML (`.yml`, `.yaml`) | Direct GitHub browser form |
   | No matching template | Explicit CLI title and body |

   If `config.yml` disables blank issues and nothing matches, ask the user instead of forcing a template.

4. Draft the Markdown body or issue-form answers under `<tmp>`.

5. Create the issue using the matching flow below.

6. Optionally verify the result when template-owned metadata or the created URL needs confirmation.
   ```bash
   gh issue view <url-or-number> -R <owner>/<repo> \
     --json title,labels,assignees,url
   ```

## Markdown Template

Pass the template's declared display `name` to `-T`, not its filename. Run from the skill root with a PTY:

```bash
GH_ISSUE_TITLE='[Prefix] Final title' \
GH_ISSUE_BODY_FILE=<tmp>/issue-body.md \
GH_EDITOR=./scripts/gh_template_editor.sh \
gh issue create -R <owner>/<repo> -T '<template-name>' --editor
```

Rules:

- Do not combine `-T` with `--body` or `--body-file`; `gh` rejects it.
- Avoid `--title` when the template owns a title prefix.
- The editor script does not require a PTY, but `gh --editor` rejects non-TTY execution before invoking it.

## YAML Issue Form

Open the selected form directly in a browser:

```text
https://github.com/<owner>/<repo>/issues/new?template=<urlencoded-template-file>
```

Fill the real fields, including required dropdowns and checkboxes. If browser automation is unavailable, open the same URL for the user; do not flatten the form into an unstructured CLI issue.

Do not use `gh issue create -T` for YAML. GitHub CLI's template API does not expose issue forms. Also avoid `gh issue create --web -T`: current web mode ignores the selected `-T` value and opens a generic issue page or chooser.

## No Matching Template

Only after discovery confirms no suitable template or form:

```bash
gh issue create -R <owner>/<repo> \
  --title 'Final title' \
  --body-file <tmp>/issue-body.md
```

Add labels, assignees, projects, or milestones only when requested.

## Script Contracts

`scripts/list_issue_templates.sh` lists local or remote `.md`, `.yml`, and `.yaml` files and extracts common metadata.

`scripts/gh_template_editor.sh` accepts:

- `GH_ISSUE_TITLE` — required final title.
- `GH_ISSUE_BODY_FILE` — preferred Markdown body file.
- `GH_ISSUE_BODY` — inline fallback body.

It preserves the scissors block appended by `gh`.

## Failure Handling

- `no templates found`: for YAML, switch to the direct browser form—the editor was never invoked. For Markdown, verify the declared template name and remote default branch.
- Non-TTY editor error: rerun the `gh --editor` command with a PTY.
- Missing expected metadata after creation: stop and inspect the template configuration before retrying.
- Missing `.github/ISSUE_TEMPLATE`: check organization-level default community health files before using a blank issue.
- Auth or project-scope failure: refresh the required scope or ask the user when assignment is mandatory.

`gh -R` targets an explicit repository and disables GitHub CLI's filesystem template lookup. Removing it does not make YAML issue forms CLI-compatible.

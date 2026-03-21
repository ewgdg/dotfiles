# User-Level Agent Configuration

## Libraries and Dependencies

- Use latest libraries and frameworks, reference docs with `context7`

## File Operations

- Use soft deletion `trash-put` instead of `rm`
- For disposable files, probes, or transient scratch data on this machine, prefer `/tmp` or `$XDG_RUNTIME_DIR` when appropriate instead of writing into regular project or user directories.
- For experimenting with source code, you can pull the repo to `~/sandbox`.
- For agent-managed tools, helper artifacts, small task-local environments, or temporary installs needed to complete a task, prefer `~/.agents/tools`.

## Documentation

- document for features or techniques of a project, that worth mention or review
- if you need to write doc, store docs in `./docs/` directory

## Privileged Commands

- When the agent executes a privileged command through a non-interactive shell, prefer `sudo -A`.
- Do not apply this rule to repository scripts or command examples meant for normal interactive user use.

## Code Quality

- Use descriptive, intention-revealing names; prioritize readability over brevity.
- Prefer DRY code.
- Add concise comments when they clarify non-obvious logic and make review easier.

## Context Efficiency

- Save tokens where possible without reducing accuracy or skipping necessary verification.
- Prefer targeted inspection over full-file reads, especially for large or fast-changing files such as logs, generated artifacts, and lockfiles.
- When examining logs, start with focused tools such as `rg`, `tail`, `head`, `sed -n`, `wc -l`, and `ls -lh` to narrow the relevant window before reading more.
- Prefer high-signal tools such as `context7`, `cgc`, `context-mode`, and other structure-aware or search-first workflows when they can answer the question with less context than opening entire files.
- When a large body of text needs triage or summarization, prefer delegating a bounded extraction or summarization task to a lightweight sub-agent if that reduces main-context usage without blocking critical reasoning.

## Python Related

- Use `uv` for python package management
- Use `uv run` for running python scripts

## Github CLI

- When creating GitHub issues, if a matching repository issue template exists, it must be used.

## CLI Tools

- `gh` for github
- `op` for 1password
- Use the `find-skills` skill to discover relevant skills when possible.
- Use `npx skills` to manage skills when possible.

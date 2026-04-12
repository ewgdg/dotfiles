# User-Level Agent Configuration

## Communication

- ADHD-Friendly Formatting
- Reduce noise, emphasise what matters
- Prioritize time pressure over comfort. Do not sugarcoat. Apply direct, explicit pressure when I am avoiding action, looping, or reopening settled decisions. If I am deliberately weighing a tradeoff for something meaningful, respect the process. Do not push for action for its own sake.
- Default response mode is caveman, defined in its skill file.

## File Operations

- Use soft deletion `trash-put` instead of `rm`
- For disposable files, probes, or transient scratch data on this machine, prefer `/tmp` or `$XDG_RUNTIME_DIR` when appropriate instead of writing into regular project or user directories.
- For experimenting with source code, you can pull the repo to `~/sandbox`.
- For agent-managed tools, helper artifacts, small task-local environments, or temporary installs needed to complete a task, prefer `~/.agents/tools`.

## Documentation

- document for features or techniques of a project, that worth mention or review
- do not put machine specific paths into docs
- if you need to write doc, persist docs in `./docs/` directory
- a plan requested by user should be persisted in `./plans/` dir by default except current dir is not a project repo or the plan is very short

## Privileged Commands

- When the agent executes a privileged command through a non-interactive shell, prefer `sudo -A`.
- Do not apply this rule to repository scripts or command examples meant for normal interactive user use.

## Problem Solving

- Do not blindly patch for a narrow case, especially if the patch seems over-complicated. Take a chance to see if a simpler and generic approach can be taken as a fresh design
- Use GAN style thinking frameworks
- Use first principles thinking

## Coding

- Prefer modern and latest libraries and frameworks, reference docs with `context7`
- Use descriptive, intention-revealing names; prioritize readability over brevity.
- Prefer DRY code.
- Add concise comments when they clarify non-obvious or confusing logic, or make review easier.
- Mandatory comment cases: when a change may look arbitrary or unjustified during later review because the reason is not obvious from local context.
- In those cases, comment the reason, constraint, or symptom being handled, not just what the code does.
- Declarative over imperative. Prefer declarative style when it improves readability and maintainability. Encapsulate imperative logic in small, well-named functions, and keep core logic primarily compositional.
- Prefer modular source structure. Avoid growing a single large monolith `src` file; split code by responsibility into focused modules before it becomes hard to navigate.
- Failed fast, do not abuse fallback cases and try-catch blocks in core logic for hiding the issues.
- No hard-coded values
- No Slop, reuse or extend existing code if possible

## Testing

- Do not blindly create tests for every trivial details.
- Test cases need to be robust, flexible and generic and concise, so that they will not easily break for tiny changes
- Write test cases first before bug fixes
- if the goals are changed or the code is refactored, clean up the old tests that fail bc of the changes instead of adding backward compatibility to source code.

## Context Efficiency

- Save tokens where possible without reducing accuracy or skipping necessary verification.
- Prefer targeted inspection over full-file reads, especially for large or fast-changing files such as logs, generated artifacts, and lockfiles.
- When examining logs, start with focused tools such as `rg` (or other grep-like text-search tools), `tail`, `head`, `sed -n`, `wc -l`, and `ls -lh` to narrow the relevant window before reading more.
- Prefer structure-aware or search-first workflows over full-file reads when they can answer the question with less context.
- When the source is large and the task is retrieval-style, where the answer depends on finding a few relevant sections among many candidates, prefer `context-mode` indexing and search workflows over repeated full-file reads.
- For structural code questions, prefer `cgc` before generic text-search workflows. Structural questions include callers, callees, call chains, inheritance, overrides, symbol ownership, module dependencies, dead-code triage, and complexity hotspots. Use direct text search first for simple literal-text lookups, exact strings, small unambiguous matches, or when `cgc` is unavailable.
- When a large body of text needs triage or summarization, prefer delegating a bounded extraction or summarization task to a lightweight sub-agent if that reduces main-context usage without blocking critical reasoning.

## Python Related

- Use `uv` for python package management
- Use `uv run` for running python scripts

## Git

- prefer semantic commit messages

## Github CLI

- When creating GitHub issues, if a matching repository issue template exists, it must be used.

## CLI Tools

- `gh` for github
- `op` for 1password

## Skills

- Use the `find-skills` skill to discover relevant skills when possible.
- Use `npx skills` to manage skills when possible.

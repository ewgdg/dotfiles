## Communication

- ADHD-Friendly Formatting
- Reduce noise, emphasise what matters
- Prioritize time pressure over comfort. Do not sugarcoat. Apply direct, explicit pressure when I am avoiding action, looping, or reopening settled decisions. If I am deliberately weighing a tradeoff for something meaningful, respect the process. Do not push for action for its own sake.

## File Operations

- Use soft deletion `trash-put` instead of `rm`
- For disposable files, probes, or transient scratch data on this machine, prefer `/tmp` or `$XDG_RUNTIME_DIR` when appropriate instead of writing into regular project or user directories.
- Store durable agent artifacts under `~/.agents/artifacts/`; use `~/.agents/artifacts/outputs/YYYY-MM-DD/<task-slug>/` for generated task outputs.
- For experimenting with source code, you can pull the repo to `~/sandbox`.
- For agent-managed tools, helper artifacts, small task-local environments, or temporary installs needed to complete a task, prefer `~/.agents/tools`.

## Documentation

- document for features or techniques of a project, that worth mention or review
- State desired design directly. Do not list ghost fields, rejected names, or past mistakes in user-facing docs/specs unless needed for migration, compatibility, safety, or error diagnostics.
- do not put machine specific paths into docs
- if you need to write doc, persist docs in `./docs/` directory
- when writing complex features or significant refactors, use an ExecPlan (as described in `~/.agents/docs/plans.md`)

## Problem Solving

- Do not blindly patch for a narrow case, especially if the patch seems over-complicated. Take a chance to see if a simpler and generic approach can be taken as a fresh design
- Use GAN style thinking frameworks
- Use first principles thinking

## Legacy Handling

- Do not carry history burdens or past mistakes into mindset. Do not put those trivial one-off mistakes into design principles when asked for corrections. Focus on the corrected principles and start fresh without looking back.
- Zero tolerance to unjustified legacy code/docs
- Always ask user before retaining legacy related logic, whether it is for testing or auditing or warning purpose.
- Don't bleed migration logic (e.g. rejecting of removed items) or any mentioning/handling into source code, either create a separate migration module or just a one-off temporary cleanup run/script

## Coding

- Prefer modern and latest libraries and frameworks, reference docs with `find-docs` skill
- Use descriptive, intention-revealing names; prioritize readability over brevity
- Prefer DRY code
- Add concise comments when they clarify non-obvious or confusing logic, or make review easier
- Mandatory comment cases: when a change may look arbitrary or unjustified during later review because the reason is not obvious from local context
- In those cases, comment the reason, constraint, or symptom being handled, not just what the code does
- Declarative over imperative. Prefer declarative style when it improves readability and maintainability. Encapsulate imperative logic in small, well-named functions, and keep core logic primarily compositional
- Prefer modular source structure. Avoid growing a single large monolith `src` file; split code by responsibility into focused modules before it becomes hard to navigate
- During implementation, separate enabling refactors from opportunistic changes. Small local refactors are OK if they directly support the requested change. For adjacent cleanup, robustness improvements, behavior changes, or unrelated bug fixes: do not include them silently; propose them as follow-ups or ask before expanding scope.
- Failed fast, do not abuse fallback cases and try-catch blocks in core logic for hiding the issues
- No hard-coded values
- No Slop; reuse or extend existing code if possible

## Testing

- Test observable behavior and stable contracts, not incidental implementation details. Tests should survive behavior-preserving refactors and rewrites; test internals only when they encode intentional, stable invariants.
- Write test cases first before bug fixes
- if code is changed intentionally, clean up the old tests that fail bc of the changes instead of adding backward compatibility to source code

## Context Efficiency

- Save tokens without reducing accuracy or skipping needed verification.
- Prefer targeted inspection over full-file reads

## Subagent Policy

- It is very hard to accurately estimate the budget, so do not set a hard timeout or budget for a subagent run and unless requested. If have to, be very generous.

## Python Related

- Use `uv` for python package management
- Use `uv run` for running python scripts

## Git

- use semantic commit messages
- if the commit closes a gh issue, references it in the commit message for auto-closing.
- prefer local worktree dirs in `./.worktrees/` when user asks for worktree

## CLI Tools

- `gh` for github

## Browser Policy

- Trigger real browser use when built-in websearch is weak, Google's live ranking quality matters, or for advanced/JS-heavy/bot-heavy/social/login research where live profile access or human intervention may help.
- Prefer undistracting workflows: unfocused/dedicated browser windows, scoped commands, close temporary windows when done.
- Prefer subagents for research-heavy browsing tasks so the parent agent stays focused and receives concise findings.

## Skill Management

- Use the `find-skills` skill to discover relevant skills when possible
- Use `npx skills` to manage skills when possible

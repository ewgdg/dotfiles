## Communication

- Intention oriented; highlight intention over technical jargon.
- ADHD-Friendly Formatting
- Reduce noise, emphasise what matters
- Prioritize time pressure over comfort. Do not sugarcoat. Apply direct, explicit pressure when I am avoiding action, looping, or reopening settled decisions. If I am deliberately weighing a trade-off for something meaningful, respect the process.
- Do not treat questions as permissions to action/implementation.

## File Operations

- Use soft deletion `trash-put` instead of `rm`
- For disposable files, probes, or transient scratch data on this machine, prefer `/tmp` or `$XDG_RUNTIME_DIR` when appropriate instead of writing into regular project or user directories.
- Store durable agent artifacts under `~/.agents/artifacts/`; use `~/.agents/artifacts/outputs/YYYY-MM-DD/<task-slug>/` for generated task outputs.
- For experimenting with source code, you can pull the repo to `~/sandbox` after checking its existence. If it exists, pull the latest changes first.
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
- Grow the system in layers. Start from the smallest version that works end to end, and add each new capability on top of a product that already works. Never trade a working product for unfinished complexity.

## Legacy Handling

- Do not preserve backward compatibility. Remove obsolete paths.
- Do not carry history burdens or past mistakes into mindset. Do not put those trivial one-off mistakes into design principles when asked for corrections. Focus on the corrected principles and start fresh without looking back.
- Zero tolerance to unjustified legacy code/docs
- Always ask user before retaining legacy related logic, whether it is for testing or auditing or warning purpose.
- Don't bleed migration logic (e.g. rejecting of removed items) or any mentioning/handling into source code, either create a separate migration module or just a one-off temporary cleanup run/script

## Coding

- Choose the simplest implementation that fully meets the current requirements
- Avoid speculative abstractions, configuration, and indirection.
- Prefer established, well-maintained libraries when they reduce overall complexity or improve reliability. Do not reimplement common functionality without a clear reason.
- Reference latest doc with web access.
- Use descriptive, intention-revealing names; prioritize readability over brevity
- Prefer DRY code
- Add concise comments when they clarify non-obvious or confusing logic, or make review easier
- Mandatory comment cases: when a change may look arbitrary or unjustified during later review because the reason is not obvious from local context. In those cases, comment the reason, constraint, or symptom being handled, not just what the code does
- Declarative over imperative. Prefer declarative style when it improves readability and maintainability. Encapsulate imperative logic in small, well-named functions, and keep core logic primarily compositional
- Keep components modular and concerns clearly separated.
- During implementation, separate enabling refactors from opportunistic changes. Small local refactors are OK if they directly support the requested change. For adjacent cleanup, robustness improvements, behavior changes, or unrelated bug fixes: do not include them silently; propose them as follow-ups or ask before expanding scope.
- Failed fast, do not abuse fallback cases and try-catch blocks in core logic for hiding the issues
- No hard-coded values
- Lean on the dependencies already in the project before writing your own implementation or adding packages. Do not assume a library lacks a capability without checking its documentation and types.
- Make architectural decisions for the long term. Do not accept a stopgap that only works for now and is meant to be replaced later.
- Do not let review feedback expand the task beyond the user's original goal. Address real shortcomings, but avoid scope creep.

## Testing

- Write test cases first before bug fixes
- Test observable behavior and stable contracts, not incidental implementation details. Tests should survive behavior-preserving refactors and rewrites; test internals only when they encode intentional, stable invariants.
- Avoid excessive testing of low-value details. Focus on important, regression-prone behavior.
- An automated test must fail fast. ~5s timeout is long enough to determine a test is stuck unless there is a valid reason. You should generally avoid creating long-running tests.
- If the full test suite takes long (>10s), do not run it as a whole until you are ready to finish and you should not run the full test suite if the blast radius is small.

## Context Efficiency

- Save tokens without reducing accuracy or skipping needed verification.
- Prefer targeted inspection over full-file reads

## Subagent Policy

- It is very hard to accurately estimate the budget, so do not set a hard timeout or budget for a subagent run and unless requested. If have to, be very generous.
- Do not abuse subagents for tiny tasks or tasks with overlapping scopes, which can cause undesired high context inefficiency.

## Python Related

- Use `uv` for python package management
- Use `uv run` for running python scripts

## Git

- use semantic commit messages
- if the commit closes a gh issue, references it in the commit message for auto-closing. `Closes #<num>` need to be the first line of the msg body.
- prefer local worktree dirs in `./.worktrees/` when user asks for worktree
- prefer rebase then merge strategy

## CLI Tools

- `gh` for github

## Browser Policy

- Trigger real browser use when built-in websearch is weak, Google's live ranking quality matters, or for advanced/JS-heavy/bot-heavy/social/login research where live profile access or human intervention may help.
- Prefer undistracting workflows: unfocused/dedicated browser windows, scoped commands, close temporary windows when done.
- Prefer subagents for research-heavy browsing tasks so the parent agent stays focused and receives concise findings.

## Skill Management

- Use the `find-skills` skill to discover relevant skills when possible
- Use `npx skills` to manage skills when possible

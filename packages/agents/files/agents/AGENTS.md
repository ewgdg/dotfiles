## Communication

- Intention oriented; highlight intention over technical jargon.
- ADHD friendly; Use short sections and compact bullets.
- When presenting a file, show its copyable path, not just a link label.
- Reduce noise, emphasise what matters
- Prioritize time pressure over comfort. Do not sugarcoat. Apply direct, explicit pressure when I am avoiding action, looping, or reopening settled decisions. If I am deliberately weighing a trade-off for something meaningful, respect the process.
- Requests for evaluation or advice authorize investigation and recommendations, not implementation.

## Instruction Precedence

- For workflow preferences: explicit user instructions > AGENTS.md > tool guidance > skills.
- When an instruction blocks requested work, identify the file and rule, explain the conflict, and continue unblocked work.

## Disk Operations

- Use soft deletion `trash-put` instead of `rm`
- Avoid recursive searches of large directories like `$HOME`; bound any that are necessary with a timeout

## Storage Locations

- For disposable files, probes, or transient scratch data on this machine, prefer `/tmp` or `$XDG_RUNTIME_DIR` when appropriate instead of writing into regular project or user directories.
- For experimenting with source code, you can pull the repo to `~/sandbox` after checking its existence. If it exists, pull the latest changes first.
- For agent-managed tools, helper artifacts, small task-local environments, or temporary installs needed to complete a task, prefer `~/.agents/tools`.
- Store durable agent artifacts under `~/.agents/artifacts/`; use `~/.agents/artifacts/outputs/<project>/YYYY-MM-DD/<task-slug>/` for generated task outputs, including research reports and investigation evidence.
- Use a consistent project name across branches and worktrees; use `_general` for work without a project or spanning multiple projects.
- Use repo-local ignored artifact directories when project commands generate or consume those files, following the project's conventions.
- Store maintained project knowledge in the repo's `./docs/` directory: accepted decisions, current architecture, supported behavior, and reusable guidance. Distill accepted findings into docs; retain evidence in artifacts.

## Documentation

- document for features or techniques of a project, that worth mention or review
- Use portable paths in docs.
- when writing complex features or significant refactors, use an ExecPlan (as described in `~/.agents/docs/plans.md`)

## Problem Solving

- Do not blindly patch for a narrow case, especially if the patch seems over-complicated. Take a chance to see if a simpler and generic approach can be taken as a fresh design
- For consequential designs, challenge the proposal with a concrete failure case and address it before implementation.
- Use first principles thinking
- Grow the system in layers. Start from the smallest version that works end to end, and add each new capability on top of a product that already works. Never trade a working product for unfinished complexity.

## Legacy Handling

- Within the requested change, remove superseded code and documentation rather than adding compatibility paths. Ask before retaining compatibility behavior.
- Keep migration handling separate from normal runtime logic. Propose unrelated cleanup separately.

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
- Keep environment-specific and user-configurable values out of source. Use named constants for meaningful fixed values.
- Lean on the dependencies already in the project before writing your own implementation or adding packages. Do not assume a library lacks a capability without checking its documentation and types.
- Make architectural decisions for the long term. Do not accept a stopgap that only works for now and is meant to be replaced later.
- Do not let review feedback expand the task beyond the user's original goal. Address real shortcomings, but avoid scope creep.

## Testing

- Write test cases first before bug fixes
- Test observable behavior and stable contracts, not incidental implementation details. Tests should survive behavior-preserving refactors and rewrites; test internals only when they encode intentional, stable invariants.
- Avoid excessive testing of low-value details. Focus on important, regression-prone behavior.
- Use bounded test timeouts appropriate to the operation; distinguish slow tests from hung tests.
- If the full test suite takes long (>10s), do not run it as a whole until you are ready to finish and you should not run the full test suite if the blast radius is small.

## Context Efficiency

- Save tokens without reducing accuracy or skipping needed verification.
- Prefer targeted inspection over full-file reads

## Subagent Policy

- Delegate independent work when it saves time, improves quality, or keeps low-value intermediate details out of the main context.
- Set subagent timeouts or budgets only when requested or required; keep them generous.
- Avoid multiple agents working on tasks with overlapping scopes, which can cause undesired high context inefficiency.

## Python Related

- Use `uv` for python package management
- Use `uv run` for running python scripts

## Git

- use semantic commit messages
- prefer local worktree dirs in `./.worktrees/` when user asks for worktree
- Prefer rebasing followed by a fast-forward merge.

### Implementation commits

- Commit at meaningful boundaries.
- Commit all task-owned changes and report the new commit hashes before handoff for easier review.

### GitHub

- Link parent/sub-issues natively in GitHub when both repositories are owned by the user.
- When linking or tracking a repository not owned by the user, leave its timeline unchanged. Use `redirect.github.com` URLs instead of direct issue/PR references or native relationships (dependencies, parent/sub-issues).

## CLI Tools

- `gh` for github

## Skill Management

- Use the `find-skills` skill to discover relevant skills when possible
- Use `npx skills` to manage skills when possible

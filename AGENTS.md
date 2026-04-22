# Repository Guidelines

## Source of Truth

- This repo is built around [`dotman`](https://github.com/ewgdg/dotman).
- If unsure about repo layout, selectors, tracking, hooks, actions, or transforms: read `README.md` first, then check upstream `dotman` docs.

## Repo Layout

- `packages/` — package definitions and managed files under `packages/<id>/files/...`
- `groups/` — reusable selector composition
- `profiles/` — variable-only profile definitions
- `scripts/` — shared helper scripts
- `repo.toml` — repo-wide defaults
- `docs/` — repo-specific notes

## Working Rules

- Use `dotman` for sync workflows.
- `dotman push` = repo → live system.
- `dotman pull` = live system → repo.
- Run Python helpers with `uv run ...`.
- Keep hooks/actions idempotent.
- Prefer package-local helpers over shared `scripts/` when scope is package-specific.
- Do not edit `*.archived` files unless explicitly asked.
- Do not commit secrets, generated state, or local-only overrides.

## Agent Behavior

- When confused, stop and read docs before changing files.
- Prefer existing repo patterns over inventing new structure.

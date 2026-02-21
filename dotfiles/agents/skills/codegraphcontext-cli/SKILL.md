---
name: codegraphcontext-cli
description: Use CodeGraphContext (cgc) CLI to index repos and answer code-structure questions (callers/callees, dependencies, search), especially for medium to large files and codebases to improve token efficiency.
---

# CodeGraphContext CLI (cgc)

Use this skill when you need *structural* answers that `rg` can’t give reliably (call graphs, call chains, dependency edges, overrides/inheritance), and you have `cgc` installed locally.

## Default workflow

1) **Discover commands/flags**

- `cgc help`
- `cgc <command> --help` (prefer this over guessing flags)

2) **Index the repo**

- From the repo root: `cgc index .`
- Verify: `cgc list` and/or `cgc stats`

3) **Answer questions using the smallest relevant command**

- Prefer high-level subcommands first: `cgc find ...` / `cgc analyze ...`
- Use raw Cypher only when needed: `cgc query ...`

4) **Report results**

- Include the exact `cgc ...` commands you ran.
- Summarize with concrete identifiers (symbol names, file paths, relationship direction).

## Output notes (Rich framing)

`cgc help` and `--help` output is plain text but often includes box-drawing frames (Rich). Treat it as normal text; copy/paste is fine.

If you need cleaner logs for parsing, pipe through `cat`:

- `cgc help | cat`

## Local database location (FalkorDB Lite default)

By default, CGC stores FalkorDB Lite data here:

- `~/.codegraphcontext/falkordb.db`
- `~/.codegraphcontext/falkordb.sock`

These can be overridden via `~/.codegraphcontext/.env` (and a project-local `.env` can override the global one).

## Safety

- Don’t run destructive commands like `cgc delete` or bundle import with `--clear` unless explicitly requested.
- If you’re about to do anything destructive, suggest a backup first (e.g. `cgc bundle export --help` → export a `.cgc` bundle).

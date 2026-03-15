---
name: codegraphcontext-cli
description: Use CodeGraphContext (cgc) CLI to index repos and answer structural code questions (callers/callees, call chains, inheritance, dependencies, search), especially when plain text search is too noisy.
---

# CodeGraphContext CLI (cgc)

Use this skill when you need graph-aware answers that `rg` cannot give reliably: callers/callees, call chains, inheritance, overrides, module dependencies, dead-code triage, or complexity hotspots.

Do **not** default to `cgc` for simple literal-text lookups. If the repo is not indexed and the question is small, `rg` plus direct file reads is usually faster and less confusing.

## Ground Rules

- Treat the installed CLI as ground truth. Run `cgc help | cat` and `cgc <command> --help | cat` instead of guessing flags from memory.
- Report the exact `cgc ...` commands you ran and summarize results with concrete identifiers: symbol names, file paths, relationship direction.
- Prefer the smallest command that answers the question. Use `find` and `analyze` before `query`.
- Many `find` and `analyze` commands search across **all indexed repositories**, not just the current repo. This is the main source of confusion. Narrow by file when supported, or fall back to repo-scoped Cypher.
- Use `cgc query` only for **read-only** Cypher. It is the escape hatch when high-level commands are too broad.
- Avoid browser-oriented output unless the user wants it. `-V` / `--visual` and `cgc visualize` are for interactive graph views.

## Default Workflow

1. **Check the local install and database state**

- `cgc version`
- `cgc doctor`
- `cgc list`
- `cgc stats .` or `cgc stats /abs/repo/path`
- `cgc config show` when backend, ignore settings, or indexing behavior matters

2. **Index or refresh the target repo**

- From the repo root: `cgc index .`
- Rebuild only when incremental results look stale: `cgc index . --force`
- For actively changing code during a longer session: `cgc watch .`

3. **Pick the smallest useful command**

- Exact symbol lookup: `cgc find name SYMBOL --type function|class|module|file`
- Fuzzy symbol lookup: `cgc find pattern auth`
- Full-text code/docstring search: `cgc find content "retry backoff"`
- Variables: `cgc find variable NAME` or `cgc analyze variable NAME`
- Functions by signature hint: `cgc find argument user_id`
- Functions by decorator: `cgc find decorator app.route`
- Callers: `cgc analyze callers FUNCTION`
- Callees: `cgc analyze calls FUNCTION`
- Call chain: `cgc analyze chain FROM_FUNC TO_FUNC`
- Module dependencies: `cgc analyze deps MODULE_NAME`
- Class hierarchy: `cgc analyze tree CLASS_NAME`
- Overrides/implementations: `cgc analyze overrides METHOD_NAME`
- Complexity hotspots: `cgc analyze complexity --limit 20`
- Dead-code triage: `cgc analyze dead-code`

4. **Disambiguate before trusting the answer**

- If the command supports `--file`, use it when the symbol name is common.
- If results span multiple repos or many generated/vendor files, do not summarize the whole table. Switch to `cgc query` and scope by path.
- For broad results, tighten the question instead of dumping a huge table.

## Repo-Scoped Cypher Patterns

Use these when high-level commands are too broad. Prefer path-based filtering because it is simple and avoids multi-repo ambiguity.

- List indexed repositories:
  - `cgc query "MATCH (r:Repository) RETURN r.name, r.path ORDER BY r.name"`

- Find an exact function inside one repo:
  - `cgc query "MATCH (f:Function {name: 'main'}) WHERE f.path STARTS WITH '/abs/repo/' RETURN DISTINCT f.name, f.path ORDER BY f.path"`

- Find matching classes/functions/modules inside one repo:
  - `cgc query "MATCH (n) WHERE (n:Function OR n:Class OR n:Module) AND n.name CONTAINS 'Auth' AND n.path STARTS WITH '/abs/repo/' RETURN DISTINCT labels(n), n.name, n.path ORDER BY n.name LIMIT 50"`

- Find callers of a function inside one repo:
  - `cgc query "MATCH (caller:Function)-[:CALLS]->(target:Function {name: 'process_data'}) WHERE caller.path STARTS WITH '/abs/repo/' RETURN DISTINCT caller.name, caller.path ORDER BY caller.path LIMIT 50"`

- Find callees of a function in a specific file:
  - `cgc query "MATCH (caller:Function {name: 'process_data'})-[:CALLS]->(callee:Function) WHERE caller.path = '/abs/repo/src/main.py' RETURN DISTINCT callee.name, callee.path ORDER BY callee.path"`

Notes:

- Use `DISTINCT` liberally in Cypher output. Variable-length traversals and duplicate edges can otherwise repeat rows.
- Use absolute paths in repo filters.
- If you do not know the repo path, get it first with `cgc list`.

## Output Notes

- Help output uses Rich framing. Treat it as normal text. If you want cleaner capture, use `| cat`.
- Many commands print setup lines such as config path, backend, and service initialization before the real result. Ignore that noise in your summary.
- Broad commands can return large, noisy tables. Do not assume a broad `find type` or `find pattern` result is exhaustive or repo-local.
- `cgc query` returns JSON-like rows and is often easier to summarize precisely than table output.

## Version and Config Drift

- Check `cgc version` before relying on examples. Installed behavior may lag or differ from the latest upstream docs.
- Check `cgc config show` for the real local backend and indexing settings. On some installations the docs/help may disagree about backend defaults or available values.
- Useful settings to inspect before blaming query quality:
  - `IGNORE_DIRS`
  - `IGNORE_HIDDEN_FILES`
  - `IGNORE_TEST_FILES`
  - `MAX_DEPTH`
  - `MAX_FILE_SIZE_MB`
  - `INDEX_VARIABLES`
  - `SCIP_INDEXER`
  - `SCIP_LANGUAGES`

If structural answers look incomplete or wrong, mention these settings explicitly in your response.

## Known CLI Caveats

- `cgc start` is deprecated. Use `cgc mcp start`.
- `cgc watching` is for MCP mode and will not show foreground CLI `cgc watch` sessions.
- `cgc analyze dead-code [PATH]` advertises a path argument, but the help text says that path-specific analysis is not yet implemented. Treat it as whole-database analysis.
- `cgc config db --help` may show fewer backend options than `cgc config show` suggests. Do not assume cross-version consistency here.

## Safety

Do not run these unless the user explicitly asks:

- `cgc delete`
- `cgc delete --all`
- `cgc bundle import --clear`
- `cgc config reset`
- `cgc index --force` when a normal `cgc index .` is sufficient

Use caution with:

- `cgc clean` because it mutates the database state, even though it is housekeeping rather than full deletion
- `cgc config set` / `cgc config db` because they change persistent local defaults

If destructive or stateful maintenance is genuinely needed, explain why first and suggest a backup path such as `cgc bundle export /tmp/repo-backup.cgc`.

## MCP, Bundles, and Admin Commands

These are not the default path for answering code questions, but they matter when the user asks for environment setup or graph transport:

- `cgc mcp ...`: configure/start the MCP server and inspect available MCP tools
- `cgc bundle ...`: export or import portable `.cgc` graph snapshots
- `cgc registry ...`: browse/download/request published bundles
- `cgc config ...`: inspect or change persistent settings

If the user only wants an answer about code structure, stay in the CLI analysis/query path and avoid drifting into setup/admin commands.

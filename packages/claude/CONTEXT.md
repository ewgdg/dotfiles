# Claude Code Package

Managed Claude Code configuration, helpers, and status-line renderers.

## Language

**Subagent identity**:
The first segment of a Claude Code subagent status row. It is the task's `name`; when unavailable, it is the `agentType` from the subagent's `agent-<id>.meta.json`. When both are unavailable, the custom renderer omits the row so Claude Code keeps its default rendering.
_Avoid_: task label

**Subagent status row**:
The complete row for a Claude Code subagent: identity, description, model label, and context percentage, in that order. Unavailable segments are omitted and the row is never renderer-truncated.

**Subagent description**:
The second segment of a Claude Code subagent status row. It is the task's `description` when supplied; it is otherwise absent.
_Avoid_: task label, task type

**Primary context indicator**:
The API-reported proportion of a context window in use. A reported zero is displayed as `0%`; when usage is unavailable but capacity is known, it is displayed as `?/200k`; when usage is known but capacity is unavailable, it is displayed as `26%/?`; when both are unavailable, the segment is absent. Values are not recalculated from other usage fields.
_Avoid_: calculated context percentage, recovered percentage

**Subagent context percentage**:
The task's `tokenCount` (its current context size) over its `contextWindowSize`, displayed as `4%/200k`. It is displayed only when both values are present and valid.
_Avoid_: token-sample recovery, cumulative token spend

**Subagent model label**:
The task's `model`, displayed verbatim, followed by `•<effort>`. Effort is the task's `effort` as written. Claude Code sends it only when the session was started with `--effort`; a level set with `/effort` is saved per model under `modelSettings` and omitted from the payload, even though the subagent runs at it. A missing effort is therefore read from `modelSettings[<model>].effortLevel` in `settings.json` under `CLAUDE_CONFIG_DIR` (default `~/.claude`), and shown as `•auto` only when none is saved.
_Avoid_: prettified model name, inferred model family

**Status-row colors**:
Color is reserved for identity, model, and context pressure. Descriptions and token counts use the terminal default color.

**Subagent row width**:
The renderer emits the complete status row regardless of the reported `columns` width. Claude Code owns any resulting clipping or wrapping.
_Avoid_: renderer truncation, field dropping

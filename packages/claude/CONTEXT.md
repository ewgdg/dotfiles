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

**Transcript tail**:
The last 1 MiB of a subagent transcript. The renderer reads only this window and takes the newest assistant entry in it; it never scans the whole transcript.
_Avoid_: transcript scan, token spend

**Primary context indicator**:
The API-reported proportion of a context window in use. A reported zero is displayed as `0%`; when usage is unavailable but capacity is known, it is displayed as `?/200k`; when usage is known but capacity is unavailable, it is displayed as `26%/?`; when both are unavailable, the segment is absent. Values are not recalculated from other usage fields.
_Avoid_: calculated context percentage, recovered percentage

**Subagent context percentage**:
The task's `tokenCount` (its current context size) over its `contextWindowSize`, displayed as `4%/200k`. When `tokenCount` is zero, which gateway-backed subagents have reported despite persisting usage, the input usage of the newest entry in the transcript tail is used instead.
_Avoid_: token-sample recovery, cumulative token spend

**Subagent model label**:
The task's `model`, displayed verbatim, followed by `•<effort>` when known. Effort is the task's `effort` when set explicitly; Claude Code omits it for inherited effort, so the newest entry in the transcript tail supplies it.
_Avoid_: prettified model name, inferred model family

**Status-row colors**:
Color is reserved for identity, model, and context pressure. Descriptions and token counts use the terminal default color.

**Subagent row width**:
The renderer emits the complete status row regardless of the reported `columns` width. Claude Code owns any resulting clipping or wrapping.
_Avoid_: renderer truncation, field dropping

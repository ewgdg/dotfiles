# Claude Code Package

Managed Claude Code configuration, helpers, and status-line renderers.

## Language

**Subagent identity**:
The first segment of a Claude Code subagent status row. It is the task's `name`; when unavailable, it is displayed as `agent`.
_Avoid_: task label, task type

**Subagent status row**:
The complete row for a Claude Code subagent: identity, description, token count, model label, and context percentage, in that order. Unavailable segments are omitted and the row is never renderer-truncated.

**Subagent description**:
The second segment of a Claude Code subagent status row. It is the task's `description` when supplied; it is otherwise absent.
_Avoid_: task label, task type

**Subagent token count**:
The current `tokenCount` reported for a Claude Code subagent, displayed in compact decimal units such as `70.8k tokens`. A reported zero is displayed as `0 tokens`; it is not inferred from historical samples.
_Avoid_: token-sample recovery, estimated token count

**Primary context indicator**:
The API-reported proportion of a context window in use. A reported zero is displayed as `0%`; when usage is unavailable but capacity is known, it is displayed as `?/200k`; when usage is known but capacity is unavailable, it is displayed as `26%/?`; when both are unavailable, the segment is absent. Values are not recalculated from other usage fields.
_Avoid_: calculated context percentage, recovered percentage

**Subagent context percentage**:
The proportion of a subagent's resolved context window represented by its current `tokenCount`, displayed with capacity as `0%/272k`. It is displayed only when both values are present and valid; it is calculated directly from those current fields.
_Avoid_: token-sample recovery, historical percentage

**Subagent model label**:
The model identifier supplied by Claude Code, displayed verbatim.
_Avoid_: prettified model name, inferred model family

**Status-row colors**:
Color is reserved for identity, model, and context pressure. Descriptions and token counts use the terminal default color.

**Subagent row width**:
The renderer emits the complete status row regardless of the reported `columns` width. Claude Code owns any resulting clipping or wrapping.
_Avoid_: renderer truncation, field dropping

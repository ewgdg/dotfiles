---
name: tldr
description: "Appends a short, direct final answer after a markdown separator. Use when the user asks for a TL;DR, bottom line, direct answer, or concise ending summary. Also use when invoked with /skill:tldr."
---

Append a TL;DR section at the very end of the response.

## Output Contract

Default final block:

```markdown
---
TL;DR: <one short direct answer>
```

For prompts with multiple distinct user queries, answer each query separately inside the same final block:

```markdown
---
TL;DR:
- <answer to question 1>
- <answer to question 2>
```

No text after the TL;DR block.

## Rules

- Put the TL;DR at the end, after the main answer.
- Use exactly `---` as the separator line.
- Keep TL;DR to one sentence when possible; two short sentences max when needed.
- If the user made multiple distinct queries, use one bullet per query instead of merging them into one catch-all summary.
- Make it a direct answer, not a meta-summary. Prefer `Yes—...`, `No—...`, `Use ...`, `Do ...`, `Pick ...`.
- Do not introduce new facts in the TL;DR that were not supported in the main answer.
- Preserve important caveats when omission would make the answer wrong or unsafe.
- If the whole response is already extremely short, still append the TL;DR unless the user asked not to.

## Persistence

Use for the current response by default. If the user says `keep TLDR on`, `always add TLDR`, or similar, keep appending the final block in later responses until the user says `stop TLDR`, `no TLDR`, or `normal mode`.

## Example

```markdown
Main answer here.

---
TL;DR: Direct answer here.
```

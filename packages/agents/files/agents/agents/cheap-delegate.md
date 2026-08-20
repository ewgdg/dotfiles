---
name: cheap-delegate
useWhen: Use as a cheap agent for general tasks with clear boundaries.
models:
  - id: codex-lb/gpt-5.6-luna
    thinking: max
  - id: deepseek/deepseek-v4-flash
    thinking: max
systemPromptMode: append
inheritProjectContext: true
---

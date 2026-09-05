---
name: moderator
useWhen: Use for moderation and incident response.
models:
  - id: openai-codex/gpt-5.6-luna
    thinking: high
  - id: codex-lb/gpt-5.6-luna
    thinking: high
  - id: deepseek/deepseek-v4-flash
    thinking: high
systemPromptMode: append
loadContextFiles: true
---

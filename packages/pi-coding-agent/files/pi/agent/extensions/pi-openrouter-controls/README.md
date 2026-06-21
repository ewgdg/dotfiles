# pi-openrouter-controls

OpenRouter-only pi extension.

## Features

- Restrict OpenRouter routing by quantizations
- Enable native OpenRouter server tools directly in request payload
  - `openrouter:web_search`
  - `openrouter:web_fetch`
- No synthetic prompt tool needed; Pi still sees the server tools in `tools` payload.

## Config

Config files, lower priority first:

1. Global agent config: `pi-openrouter-controls.json`
2. Project config: `.pi/pi-openrouter-controls.json`

JSON uses snake_case.

```json
{
  "openrouter": {
    "quantizations": ["bf16", "fp16"],
    "web_search": true,
    "web_fetch": false
  }
}
```

## Commands

```text
/openrouter-controls status
/openrouter-controls reload
```

Edit JSON manually, then run `/openrouter-controls reload`.

## Notes

- `openrouter:web_search` = search only.
- `openrouter:web_fetch` = fetch/extract page or PDF content.
- `quantizations` is forwarded to OpenRouter's request `provider` filter.

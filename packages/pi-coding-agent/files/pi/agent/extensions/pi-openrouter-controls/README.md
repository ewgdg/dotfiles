# pi-openrouter-controls

OpenRouter-only pi extension.

## Features

- Restrict OpenRouter routing by quantizations.

## Config

Config files, lower priority first:

1. Global agent config: `pi-openrouter-controls.json`
2. Project config: `.pi/pi-openrouter-controls.json`

JSON uses snake_case.

```json
{
  "openrouter": {
    "quantizations": ["bf16", "fp16"]
  }
}
```

## Commands

```text
/openrouter-controls status
/openrouter-controls reload
```

Edit JSON manually, then run `/openrouter-controls reload`.


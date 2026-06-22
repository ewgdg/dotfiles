# pi-openrouter-controls

OpenRouter-only pi extension.

## Features

- Send stable `session_id` to OpenRouter so prompt-cache routing can stick to the same upstream.
  - Uses pi's session ID, not an ID returned by OpenRouter.
  - If a custom pi session ID is longer than OpenRouter's 256-character limit, the extension sends a stable SHA-256 based ID instead.
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

Valid quantizations: `int4`, `int8`, `fp4`, `fp6`, `fp8`, `fp16`, `bf16`, `fp32`.

Set project `quantizations` to `[]` to clear a global quantization restriction for that project.

## Commands

```text
/openrouter-controls status
/openrouter-controls reload
```

Edit JSON manually, then run `/openrouter-controls reload`.


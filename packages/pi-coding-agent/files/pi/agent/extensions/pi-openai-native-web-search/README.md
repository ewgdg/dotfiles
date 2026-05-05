# pi-openai-native-web-search

Adds OpenAI native web search to pi. Current implementation supports Pi's `openai-codex` provider only.

Design copied from `@howaboua/pi-codex-conversion`, but without its prompt/tool adapter:

1. Register a synthetic `web_search` tool so the model can choose it.
2. Keep that tool active only for `openai-codex` models.
3. Rewrite pi's serialized function tool into Codex's native Responses API tool right before provider request.

## What it changes

Pi serializes active tools as function tools, e.g.:

```json
{
  "type": "function",
  "name": "web_search"
}
```

Before the provider request, this extension rewrites that function tool to Codex's native Responses API tool:

```json
{
  "type": "web_search",
  "external_web_access": true
}
```

`external_web_access: true` means live web. `false` means cached web.

For non-Spark Codex models, it defaults to:

```json
"search_content_types": ["text", "image"]
```

Set `"searchContentTypes"` to override.

## Config

Use `pi-openai-native-web-search.json` in the global pi agent config dir, or in a project `.pi/` dir. Project config overrides global config.

```json
{
  "mode": "live",
  "allowedDomains": ["example.com", "openai.com"],
  "searchContextSize": "medium",
  "userLocation": {
    "country": "US",
    "region": "CA",
    "city": "San Francisco",
    "timezone": "America/Los_Angeles"
  },
  "searchContentTypes": ["text", "image"]
}
```

All fields are optional. `mode` defaults to `live`.

Runtime command:

```text
/openai-native-web-search
/openai-native-web-search live
/openai-native-web-search cached
/openai-native-web-search disabled
```

Without an argument, `/openai-native-web-search` opens a picker. Runtime changes are session-only; edit the JSON config to persist defaults.

Run `/reload` after changing extension code. Start a new session or `/reload` after changing config.

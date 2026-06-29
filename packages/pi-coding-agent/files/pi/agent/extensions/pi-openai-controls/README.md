# pi-openai-controls

Personal pi extension for OpenAI provider controls. It is named for the whole OpenAI family, but the native web-search path is currently Codex-only because pi exposes Codex Responses payloads in the needed shape.

## Features

- OpenAI Responses `service_tier` control
  - `auto`, `default`, `flex`, `priority`
  - footer hidden for `auto`
  - footer labels: `🚀std`, `🚀flex`, `🚀prio`
- OpenAI Codex native web search
  - synthetic `web_search` tool in pi
  - rewritten to native OpenAI Responses `type = "web_search"` before request send
  - `live`, `cached`, or `disabled`
- Separate footer statuses for web search and service tier so symbols/colors do not visually merge.

## Commands

```text
/openai-controls
/openai-controls status
/openai-controls reload
/openai-controls service-tier auto
/openai-controls service-tier default
/openai-controls service-tier flex
/openai-controls service-tier priority
/openai-controls web-search live
/openai-controls web-search cached
/openai-controls web-search disabled
```

Aliases accepted for service tier:

```text
std -> default
standard -> default
prio -> priority
```

Runtime command changes are written to JSON config immediately, so they survive new sessions and pi restarts. Edit JSON manually only when you prefer direct file edits, then run `/openai-controls reload`.

## Config

Config files, lower priority first:

1. Global agent config: `extensions/pi-openai-controls/config.json`
2. Project config: `.pi/extensions/pi-openai-controls/config.json`

Project config overrides global config. JSON uses snake_case.

```json
{
  "web_search": {
    "mode": "live",
    "search_context_size": "medium",
    "search_content_types": ["text", "image"],
    "allowed_domains": [],
    "user_location": {
      "country": "US",
      "region": "CA",
      "city": "San Francisco",
      "timezone": "America/Los_Angeles"
    }
  },
  "service_tier": {
    "default": "auto"
  }
}
```

All fields are optional. `/openai-controls service-tier ...` and `/openai-controls web-search ...` update this JSON file while preserving other fields.

## Service-tier notes

OpenAI Responses API `service_tier` values are `auto`, `default`, `flex`, and `priority`.

- `auto`: use Project service-tier setting; usually standard/default unless configured otherwise
- `default`: standard processing
- `flex`: cheaper/slower processing, limited availability
- `priority`: faster/pricier processing

Pi's `openai-codex` provider uses ChatGPT's Codex backend, not the public Responses API endpoint. That backend currently rejects explicit `default` and `flex`; this extension therefore omits `service_tier` for `auto`, `default`, and `flex` on `openai-codex`, and only sends `priority`.

## Implementation notes

Pi serializes active tools as function tools. This extension registers a synthetic `web_search` tool and rewrites:

```json
{ "type": "function", "name": "web_search" }
```

into Codex native web search:

```json
{ "type": "web_search", "external_web_access": true }
```

For non-Spark Codex models, web search defaults to:

```json
"search_content_types": ["text", "image"]
```

Service-tier control uses `before_provider_request`, so it modifies the final provider payload at the edge. Cost accounting follows whatever pi/OpenAI reports; manual payload rewrites may be less exact than first-class pi settings if the provider omits service-tier data.

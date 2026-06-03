# Browser policy

Goal: browser work should not steal focus or disrupt current niri workspace. Prefer undistracting workflows over convenience.

## Defaults

- Prefer a subagent for research-heavy tasks: search engines, Reddit, X/Twitter, docs hopping, multi-page browsing, source gathering.
- Prefer medium thinking for browser research subagents: enough source judgment without burning high-thinking cost.
- Keep parent agent in control; subagent returns concise findings, source URLs, and uncertainty.
- Prefer visible but unfocused browser work when human intervention may be needed.
- Never use unscoped browser commands when a dedicated window id is available.
- Close temporary browser windows when task ends unless user asks to keep them open.
- Treat live browser/profile data as sensitive. Do not quote private sidebars, account names, notifications, cookies, localStorage, or unrelated logged-in context.

## Surf dedicated window pattern

Use Surf's own agent marker window. It creates a tab titled `Surf Agent`, which niri can match and keep unfocused.

For each task:

```bash
win=$(surf window.new --unfocused | grep -oP 'Window \K[0-9]+')
surf --window-id "$win" go "https://example.com"
surf --window-id "$win" page.text
# ...more scoped commands...
surf window.close "$win"
```

Rules:

- Always pass `--window-id "$win"` after creating the window.
- Avoid global `surf go`, `surf tab.new`, `surf page.text`, `surf read`, `surf js`.
- Create window before first navigation.
- Close the window at the end of the research task.
- If human intervention is needed, leave the window open and tell user the window/page.

Persistent/long-running session reuse:

- Use persistent window only when intentional; per-task fresh windows are default.
- Cache the Surf window id in runtime/tmp (`$XDG_RUNTIME_DIR`, else `$TMPDIR`, else `/tmp`) and reuse it while the window still exists.
- If cached id is stale or missing, create a new unfocused Surf window and update the cache.

## Surf extraction choice

- Quick visible text: `surf --window-id "$win" page.text`
- Clickable refs/structure: `surf --window-id "$win" page.read --compact --depth 4`
- Structured extraction: `surf --window-id "$win" js --file /tmp/extract.js`
- Heavy JS/social pages: prefer `page.text` first; use `js` scoped to `main`, `article`, or known selectors if more structure needed.

## agent-browser use

Use agent-browser when its strengths matter:

- headless/no-visible-window work
- React introspection
- profiling/tracing/video
- complex repeatable automation
- cloud/browser-provider workflows

For live Chrome/CDP, expect permission dialogs and possible focus/session quirks. Do not use CDP live Chrome for routine research if Surf works.

## Niri note

Niri rule should keep Surf agent marker unfocused:

```kdl
window-rule {
    match app-id="google-chrome" title=r#"(?i)Surf Agent"#
    open-on-workspace "stash"
    open-focused false
    open-maximized true
}
```

Workspace routing may be best-effort if title arrives after initial placement. Focus avoidance matters more than workspace placement.

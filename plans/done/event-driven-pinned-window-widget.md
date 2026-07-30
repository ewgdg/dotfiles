# Event-driven pinned window widget

## Goal

Replace the Noctalia pinned-window widget's 500 ms subprocess polling with one
event-driven plugin service that publishes shared state to every bar instance.

## Intention

Keep `pinned-window.sh` as the public Niri command and persisted-state owner.
Move synchronization behind a Noctalia service entry: it performs one initial
status read, listens to Niri's event stream for changes to the pinned window,
and publishes the current status through Noctalia shared state. Bar widgets only
render shared state and submit actions.

## Scope & Constraints

- Do not add another systemd unit; the service entry is hosted by Noctalia under
  the existing `niri-shell.service`.
- Preserve the helper CLI commands and runtime JSON state contract.
- Notify the plugin service after helper commands that change pin ownership,
  while allowing those commands to work when Noctalia is unavailable.
- Keep one Niri event stream per enabled plugin, independent of bar/output count.
- Remove periodic widget subprocess polling entirely.
- Test only the confirmed public seams: helper CLI/state behavior, Noctalia's
  plugin linter, and real live Noctalia/Niri behavior.
- Do not change unrelated Noctalia configuration warnings or adjacent Niri
  helpers.
- Let the user run `dotman push`; live diagnostic deployment may use temporary
  copies only when it does not overwrite managed source.

## Work Plan

1. Add a failing helper CLI test proving pin/clear state changes notify the
   Noctalia service without making Noctalia availability a command dependency.
2. Implement the minimal helper notification behavior and make the focused test
   pass.
3. Add the Noctalia service entry, shared-state widget adapter, and manifest
   declaration; remove widget polling.
4. Validate manifest/config contracts and exercise the service against the real
   Niri event stream and bar.
5. Run focused and full repository tests, inspect the final diff, and complete
   this plan.

## Validation

- `env -u NO_COLOR uv run pytest -q tests/test_pinned_window.py`
- `noctalia plugins lint packages/noctalia/files/local/share/noctalia/plugins/pinned-window`
- Real Niri/Noctalia validation: pin, title update, clear/close, bar rendering,
  and process inspection confirming no repeated `status-json` polling.
- `env -u NO_COLOR uv run pytest -q`
- `git diff --check`

## Progress

- [x] Public test seams confirmed with the user.
- [x] Helper notification test observed failing.
- [x] Helper notification behavior implemented and focused tests green.
- [x] Plugin service and render-only widget implemented.
- [x] Real compositor behavior validated.
- [x] Full validation and review complete.

## Decisions

- The runtime state file remains the durable seam for Niri-side helpers.
- Noctalia shared state is the internal seam between the single service entry
  and any number of widget instances.
- A dedicated plugin-owned Niri stream is preferable to coupling this feature
  into the generic event-stream-rules daemon.

## Surprises & Discoveries

- Noctalia hosts service entries inside the existing shell process, so the
  event-stream owner needs no separate systemd unit.
- A title-only Ghostty rule was too late to prevent a disposable validation
  window from briefly taking focus. The corrected probe used the existing
  app-id-based `surf-agent` rule, stayed unfocused, and was closed after the
  check.
- The first long-lived Alacritty probe used a fixed command-line title, which
  ignored its later title escape. A dynamic title probe confirmed the actual
  Niri title event and bar update.
- The full repository suite currently reports `164 passed, 1 failed`. The
  failure is the pre-existing Faugus local-state expectation, which omits the
  already-present `start-fullscreen`, `enable-hdr`, `smaller-banners`, and
  `start-maximized` keys and is outside this plan.

## Outcomes & Retrospective

- The bar no longer launches `status-json` every 500 ms. One Noctalia service
  performs the initial read, owns one persistent `niri msg -j event-stream`
  child, and publishes shared state to render-only widget instances.
- Pin, toggle, and clear notify the service immediately while remaining
  successful when Noctalia is unavailable.
- Live validation confirmed one Niri stream, no repeating status subprocess,
  immediate pin/clear rendering, title changes rendered on the real bar, and
  close events clearing the runtime state without a manual `status-json` probe.
- Focused tests passed (`3 passed`), plugin lint passed with zero errors and
  warnings, config validation passed apart from the unrelated existing
  `shell.launcher.session_search` warning, shell syntax passed, and
  `git diff --check` passed. `shellcheck` was unavailable.

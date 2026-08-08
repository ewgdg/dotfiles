# Rename the bridge to xembed-sni-proxy

## Goal

Rename the maintained bridge implementation, executable, Python package, and niri app-id to `xembed-sni-proxy`, while retaining the Dotman package id `linux/xembedsniproxy` and systemd unit name `xembedsniproxy.service`.

## Intention

The implementation is no longer merely the upstream `wine-sni-bridge.py` script: it handles generic XEmbed clients and contains substantial local lifecycle, registration, and identity behavior. Give the implementation a neutral identity and a standard Python `src/` layout without colliding with Plasma's `/usr/bin/xembedsniproxy`.

## Scope & Constraints

- Keep `packages/linux/xembedsniproxy/` and `id = "linux/xembedsniproxy"`.
- Keep `xembedsniproxy.service`; Plasma's unit is separately named `plasma-xembedsniproxy.service`.
- Use `xembed-sni-proxy` for the distribution, executable, and WM_CLASS/app-id.
- Use `xembed_sni_proxy` for the import package and `XEmbedSNIProxy` for the main class.
- Move implementation to `src/xembed_sni_proxy/`.
- Do not provide a `wine-sni-bridge` compatibility executable or import alias.
- Preserve the user's unrelated `hidden true` niri rule change.
- The user performs `dotman push`; do not run it on their behalf.
- Avoid leaving the live service broken during the repo-to-live cutover.

## Work Plan

1. Add regression assertions for the new project identity, executable, and WM_CLASS.
2. Move the implementation into `src/xembed_sni_proxy/bridge.py` with the console script as its single executable interface.
3. Update Python imports, class name, packaging metadata, Dotman probe, service `ExecStart`, README, tests, and niri rule.
4. Run targeted tests, package build/install validation, source scans, and diff checks.
5. Ask the user to run `dotman push linux/xembedsniproxy linux/niri` (or their normal selector) to update live files and install the new executable.
6. After the push, restart the retained service, verify the new process/app-id and both live SNI items, uninstall the obsolete uv tool, and remove this plan to `plans/done/`.

## Validation

- `uv run --with python-xlib --with dbus-python pytest -q tests/test_xembed_sni_proxy.py`
- `uv build packages/linux/xembedsniproxy`
- A temporary `uv tool install --editable` exposes `xembed-sni-proxy --help`.
- No implementation/config references to the former executable, module, class, or app-id remain except explicit upstream provenance in README.
- `git diff --check`
- After user push: service active under `xembedsniproxy.service`, command is `xembed-sni-proxy`, WM_CLASS is `xembed-sni-proxy`, and all active XEmbed children are registered with the watcher.

## Progress

- [x] Naming decision made.
- [x] Existing KDE command/unit collision checked.
- [x] Regression assertions added.
- [x] Source/package rename complete.
- [x] Static and package validation complete.
- [x] User-side Dotman push complete.
- [x] Live cutover and obsolete tool cleanup complete.

## Surprises & Discoveries

- The live systemd and niri files are regular Dotman-managed copies, not links to the repository. Repository edits therefore cannot complete the cutover without a user-run push.
- Moving the editable module makes the old executable unsuitable for a future restart. The new uv tool is installed and a temporary runtime systemd override points the next restart at `xembed-sni-proxy`; the currently running process remains uninterrupted until the user pushes the persistent files.

## Outcomes & Retrospective

- The retained `xembedsniproxy.service` now runs `%h/.local/bin/xembed-sni-proxy` from the new editable project; the temporary runtime override was removed before restart.
- The tray owner advertises `WM_NAME` and `WM_CLASS` as `xembed-sni-proxy`, and the same pre-restart XEmbed icon XID re-docked with its `Battle.net` title and Active SNI status.
- The obsolete uv tool and `wine-sni-bridge` executable were removed. Plasma's distinct static `plasma-xembedsniproxy.service` remains untouched.
- Keeping the console script as the sole executable interface made `__main__.py` unnecessary; it was removed before final validation.

## Decisions

- `xembed-sni-proxy` rather than `xembedsniproxy`: the latter already exists at `/usr/bin/xembedsniproxy` from Plasma.
- Retain the Dotman package and service names because they describe the selected system role and do not collide with Plasma's `plasma-xembedsniproxy.service`.
- Use a `src/` package now that the code is a maintained implementation rather than a minimally patched vendored script.
- Keep the console script as the only executable interface; a redundant `python -m` adapter does not earn its own seam.

# Port native XEmbed input forwarding

## Goal

Make tray activation reach the embedded application through native X11 input semantics so Wine can interpret single-click and double-click itself, while retaining the maintained proxy's tooltip and lifecycle behavior.

## Intention

Replace the title-based application-window mapping fallback with KDE xembedsniproxy's generic model: each embedded icon lives in a transparent input-shaped host whose input region is enabled only while forwarding input.

## Scope & constraints

- Preserve SNI tooltip inference, icon extraction, registration, Wine fallback-tray cleanup, right-click behavior, and graceful icon release.
- Forward one X11 press/release pair for every SNI activation. Do not infer double-clicks or map application windows.
- Separate tray-selection ownership from per-icon hosting so one icon can be positioned without affecting other icons.
- Use python-xlib's Composite, Shape, and XTest extensions. Fail fast if any required extension is unavailable.
- Keep the helper generic. Do not add Battle.net identifiers or application-window matching.
- The user performs Dotman push. Do not run it.

## Work plan

1. Replace the fallback regression test with one that drives SNI Activate and asserts observable native host operations and a single forwarded click.
2. Add the smallest per-icon host needed to make that test pass, including transparent override-redirect windows, idle empty input shape, activation placement, pointer warp, and delayed deactivation.
3. Move icon docking and release from the tray-selection owner to the per-icon host.
4. Use direct delivery only when the embedded top-level selects button input; otherwise use XTest, and always prefer XTest under Niri/Xwayland-satellite.
5. Update Niri identity/rules and package documentation for the new helper-window behavior.
6. Run targeted tests, static checks, package build, and a live A/B validation against the KDE proxy.

## Validation

- `uv run --with python-xlib --with dbus-python pytest -q tests/test_xembed_sni_proxy.py`
- `uv build packages/linux/xembedsniproxy`
- `git diff --check`
- Source scan confirms no double-activation timer or application-window mapping fallback remains.
- Live: hover shows `Battle.net`; single-click, double-click, and right-click are handled by Wine; no helper steals focus or consumes layout.

## Progress

- [x] KDE behavior reproduced live as the known-good reference.
- [x] Behavioral test seam selected: SNI activation to observable X11 host operations.
- [x] Native activation regression test went red against title-based mapping.
- [x] Per-icon native host implemented.
- [x] Targeted automated validation passes.
- [x] Live D-Bus activation remapped an explicitly unmapped Battle.net window.
- [x] Captured Noctalia's actual single- and double-activation calls and the leaked Wine tooltip surface.
- [x] A Wine tray probe received `DOWN → UP → DBLCLK → UP` and right-button events through the custom proxy.
- [x] The native Wine tooltip remains unmapped after activation.
- [x] User confirmed reliable double-click and right-click through the actual Noctalia icon after restarting Battle.net.

## Surprises & discoveries

- Xwayland-satellite exposes KDE's override-redirect icon host to Niri as `app_id=xembedsniproxy`; without a rule, its transparent surface occupied a large tiled column.
- Battle.net advertises a button event mask, but Proton rejects the resulting direct synthetic events intermittently under Xwayland-satellite. Niri therefore uses XTest regardless of the client mask; other X11 environments retain KDE's direct-or-XTest selection.
- The existing Niri rule can keep the custom host hidden on the stash workspace without breaking native activation. X11 still reports the host as mapped and XTest reaches the embedded icon as non-synthetic core events.
- A real XTest probe initially missed because placement, Shape, and pointer-warp requests had not been synchronized before injection. Adding an X sync made press and release arrive reliably.
- Review caught an incorrect python-xlib `warp_pointer` argument order that permissive test doubles had hidden. The test fake now has python-xlib's real signature, and the implementation warps to the calculated icon point.
- Noctalia emitted two `Activate` calls 193 ms apart, so its pinned icon correctly preserved the physical double-click. The intermittent delivery came later: Niri/Xwayland-satellite assigned the helper a different root position than the SNI coordinates, and Wine discarded button events whose root coordinates did not match the embedded icon.
- A minimal Wine tray probe made the mismatch deterministic. KDE and the port produced only `WM_MOUSEMOVE` at Noctalia's coordinates; using the compositor-assigned host coordinates produced `WM_LBUTTONDOWN → WM_LBUTTONUP → WM_LBUTTONDBLCLK → WM_LBUTTONUP`.
- Wine also mapped a 53×18 native tooltip window about 500 ms after the proxy warped into the icon. Xwayland-satellite exposed this transient dialog as the focus-ring popup the user reported. Emptying the input shape did not produce a pointer leave; re-targeting the same root coordinate after direct delivery did, without breaking double-click tracking.
- The broad Niri rule matching only the `Battle.net` title was unrelated to restoration and could catch auxiliary surfaces, so it was removed. The existing helper rule keeps the host hidden on the stash workspace; its original tiling policy remains compatible with native input.
- Final review caught that each host selects `SubstructureRedirectMask` but the initial port ignored `MapRequest` and `ConfigureRequest`. The bridge now honors client remaps and clamps requested icon sizes to 32px, preserving Active/Passive recovery without letting the embedded icon outgrow its host.
- A descendant-only button subscription cannot receive a direct event sent with propagation disabled to the embedded top-level. Those clients now use XTest instead.
- KDE maps SNI scroll direction to one native X11 wheel click at the current pointer position. The port now preserves the same vertical and horizontal behavior.
- Moving the Niri host offscreen during delayed XTest deactivation invalidated Proton's click state. Keeping the host fixed, emptying its input region, and re-targeting the same root point made Battle.net restoration and native menus reliable.
- Battle.net exposes its context menu as a normal Wine/X11 toplevel. Focus-driven dismissal works when focus moves to another Wine/X11 surface, but Xwayland-satellite cannot report a native Wayland focus transition back to that X11 menu.

## Decisions

- Preserve the public SNI methods as the caller interface. Hide X11 placement and injection details inside the bridge.
- Remove the mapping fallback rather than retaining it behind a secondary path.
- On Niri, trust the compositor-assigned X11 host geometry instead of issuing an absolute X configure request that the xdg-toplevel protocol cannot honor.
- Use XTest on Niri so Proton receives compositor-routed native events. Preserve KDE's client-mask selection elsewhere.
- Keep the host position stable across activation. Drop its Shape input region and force a pointer leave at the same root point so click state survives without leaking a Wine tooltip window.

## Outcomes & retrospective

The proxy now publishes useful tooltips and preserves application-owned single-click, double-click, right-click, and scroll semantics without mapping application windows. The selection owner remains outside compositor layout, per-icon hosts remain hidden and non-focusable, and embedded icons recover from client map and resize requests. Automated probes and the actual pinned Noctalia Battle.net icon both validated native input; the user accepted Xwayland-satellite's cross-protocol menu-focus limitation.

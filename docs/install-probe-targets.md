# Install Probe Targets

Use dotman probe targets for packages whose main job is installing or updating software.
Probe targets model live requirements directly instead of relying on tracked marker files that can go stale.

## Target Pattern

Use a probe target when a package has no user-facing config target, or when an install/update action should only run if live state is missing or outdated.
Only use probes when the check is cheap and safe enough to run during dotman planning; avoid network-heavy, slow, flaky, or side-effect-prone checks unless the saved install/build cost clearly justifies them.
Prefer one probe target per installable tool/package so dotman can run only the missing or outdated item's hook.

Probe contract:

- exit `0` when action is needed
- exit `100` when live state is already current/noop
- any other non-zero exit is a hard failure
- keep probes side-effect-free
- put install/update commands in target hooks
- use `$DOTMAN_PACKAGE_ROOT` for package-local probe scripts and `$DOTMAN_REPO_ROOT` for shared repo scripts

Example:

```toml
id = "go-lang"
description = "Go language toolchain bootstrap"

[targets.go_toolchain_installed]
sync_policy = "push-only"
probe = '{{ PROBE_PACKAGES_INSTALLED }} go'

[targets.go_toolchain_installed.hooks]
pre_push = "{{ INSTALL }} go"
```

## What To Check

Every plan runs every probe, so probe cost adds up. Prefer the cheapest reliable live-state check.
Running a tool to check it (`--version`, `npm prefix`, `uv run` helpers) pays its startup on every plan, and interpreter-based CLIs are slow: Node or Python startup costs 50–350ms per call, while `command -v` costs about 1ms.
Run the tool only when a version or health check catches a real failure that a cheaper check misses. Network checks follow the same rule; see custom Git builds below.

In order of preference:

1. Use `{{ PROBE_COMMANDS_ON_PATH }} <command>...` when the requirement is a CLI on `PATH` and the command name is the contract. It wraps `command -v` with the probe exit contract.
2. Use missing-only package-manager checks through `{{ PROBE_PACKAGES_INSTALLED }}` when the requirement is a package identity, bundle, library, font, theme, service, portal, or anything without a reliable command. OS profiles bind that variable to the matching probe helper (`probe_arch_packages_installed.sh` or `probe_homebrew_packages_installed.sh`).
3. Use package-local probes for custom or tool-managed installs when they need richer state checks.

Use package-manager checks for:

- Arch/AUR packages managed through `{{ INSTALL }}`
- Homebrew packages managed through `{{ INSTALL }}`

Use `{{ PROBE_APPIMAGE_INSTALLED }}` / `{{ APPIMAGE_INSTALL }}` (Linux) for AppImages that update themselves:
pass `--name <name>` to both, `--url <url>` to install, and `--link-command` to both when the app should get `~/.local/bin/<name>`.
Pass `--drop-mime-types` to install when the app registers its own URL-handler entry at runtime, so the menu entry does not duplicate it in "Open with" choosers.
Install puts the file at `~/Applications/<name>.AppImage`, adds the desktop entry and icons, and records them in `~/.local/state/appimages/<name>.files`. The probe and re-integration read that record instead of scanning shared directories.
Never re-download from a probe; the app owns later updates. Repacking or external updaters would fight the app's own updater.
Renaming `<name>` makes a new install; remove the old one's recorded files, AppImage, and command link.

Use package-local probes for custom or tool-managed installs:

- custom Git builds: use one target that checks the package is installed, plus an `on_demand = true` target that compares the installed Git hash with upstream `HEAD`; the update runner selects that target by name (see `packages/niri-custom-git/README.md`)
- Rust toolchain setup: check required capability state (`rustup`, active toolchain, required components), not newest versions
- Go/npm tool installs: check the command with `{{ PROBE_COMMANDS_ON_PATH }}`; avoid making every push fragile just to chase latest

## Marker Files

Install marker files are legacy fallback state. See `docs/install-marker-packages.md` for that older pattern.
Prefer probe targets unless a real file target is still needed and a probe cannot model the requirement.

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

Prefer the cheapest reliable live-state check:

1. Use command probes such as `command -v <tool>` when the requirement is a CLI on `PATH` and the command name is the contract.
2. Use missing-only package-manager checks through `{{ PROBE_PACKAGES_INSTALLED }}` when the requirement is a package identity, bundle, library, font, theme, service, portal, or anything without a reliable command. OS profiles bind that variable to the matching probe helper (`probe_arch_packages_installed.sh` or `probe_homebrew_packages_installed.sh`).
3. Use package-local probes for custom or tool-managed installs when they need richer state checks.

Use package-manager checks for:

- Arch/AUR packages managed through `{{ INSTALL }}`
- Homebrew packages managed through `{{ INSTALL }}`

Use package-local probes for custom or tool-managed installs:

- custom Git builds: compare installed Git hash with upstream `HEAD` when reliable
- Rust toolchain setup: check required capability state (`rustup`, active toolchain, required components), not newest versions
- Go/npm tool installs: check command/version state when cheap; avoid making every push fragile just to chase latest

## Marker Files

Install marker files are legacy fallback state. See `docs/install-marker-packages.md` for that older pattern.
Prefer probe targets unless a real file target is still needed and a probe cannot model the requirement.

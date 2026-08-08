# Topgrade upgrade workflow

## Decision

Use **[Topgrade](https://github.com/topgrade-rs/topgrade)** as the interactive orchestrator and expose it as an `upgrade` command that executes `topgrade`.

Implement this as a dedicated `topgrade` dotman package. The package owns both
the managed Topgrade configuration and a standalone `upgrade` executable under
`~/.local/bin`. Keep the command independent of shell aliases so it is directly
testable and available from any shell. With no subcommand, `upgrade` delegates
to Topgrade; service deployment is the explicit `upgrade services` subcommand.
Reserve only that exact subcommand and forward every other argument unchanged
to Topgrade, allowing selective operations such as `upgrade --only cargo`.

Select the package on both Arch and macOS host profiles. `paru` owns Topgrade
and system packages on Arch; Homebrew owns them on macOS. Topgrade runs only the
ecosystem steps applicable to the current host. An explicitly requested
`upgrade services` must fail with an actionable error when the services
repository or its updater is unavailable; it must not silently succeed.

Install Topgrade through the host package manager. Pin the Arch configuration to
`paru`, the package helper owned by the dotfiles bootstrap and install helpers,
rather than depending on auto-detection.

Do not make package upgrades unattended and do not default to `--yes`. AUR builds, pacnew review, and runtime/service changes need a human present.

Preserve Topgrade's native failure prompt: retry the step, open a repair shell,
continue while recording the failure, or quit. Do not configure automatic
retries. The command must return a nonzero status when any step remains failed.

## Managed Topgrade policy

```toml
# ~/.config/topgrade.toml
[misc]
# The package manager, not Topgrade's standalone updater, owns this executable.
no_self_update = true
ask_retry = true
auto_retry = 0
disable = ["containers"]

[linux]
arch_package_manager = "paru"

[git]
# Pull only explicitly selected repositories; never infer repositories from
# shell, editor, or dotfiles locations.
pull_predefined = false
repos = ["~/Projects/dotfiles"]

[cargo]
git = true
```

Topgrade's default Git step considers paths such as `~/.config/nvim` and shell
configuration repositories. Disable predefined discovery so `upgrade` cannot
broadly mutate configuration checkouts. Allowlist only the dotfiles repository:
Git may update the repository, while `dotman push` remains the only operation
that updates the live system from it.
For those repositories, Topgrade uses `git pull --ff-only
--recurse-submodules`; divergence fails instead of creating a merge commit or
overwriting history. A dirty dotfiles worktree is allowed: Git advances it only
when incoming changes preserve the local edits and fails when they would be
overwritten. [Topgrade configuration](https://github.com/topgrade-rs/topgrade/blob/main/config.example.toml) · [Git step source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/git.rs)

Do not merge upstream remotes or push repositories during `upgrade`. Fork
synchronization requires repository-specific validation and is outside this
workstation-maintenance command.

## Executable ownership

The package manager that installed an executable is its sole upgrade owner.
Disable or skip a tool's self-update when `paru`, Homebrew, or another system
package manager owns that executable. Use self-update only for standalone
installations.

This ownership rule applies to the manager executable, not its payloads. For
example, `paru` upgrades the `rustup` executable on the Arch profile (the
install script prefers the native package), while `uv tool upgrade --all` and
`rustup update` upgrade the tools and toolchains they manage. `uv` itself is
bootstrap-installed standalone by `init.sh`; a native `uv` is tolerated because
`init.sh` skips when one already exists, and the native package manager then
owns it.

## Coverage

Install updater prerequisites through their owning dotman packages rather than
bootstrapping them inside `upgrade`. In particular, `go-lang` installs `gup`
with `go install github.com/nao1215/gup@latest`; Topgrade then uses the installed
`gup` for routine Go binary updates.

| Concern | Owner / Topgrade step | Notes |
| --- | --- | --- |
| Arch repos, AUR, and Arch-owned executables (`bun`, `nvim`, Docker) | `paru` system step | Runs the normal full Arch/AUR upgrade. |
| Homebrew on the macOS profile | Brew steps | Automatically used only where `brew` exists. |
| uv executable, uv tools, and uv-managed Pythons | `Uv` | `init.sh` bootstraps `uv` standalone; the step self-updates it and upgrades its tools and managed Pythons. A native `uv` is tolerated (`init.sh` skips when one already exists) and stays owned by its package manager. [uv tools](https://docs.astral.sh/uv/concepts/tools/) · [Topgrade uv step](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/generic.rs) |
| npm and Bun global packages | npm and Bun-package steps | Update globally installed tools only. Do not search project directories, change project dependencies, or rewrite project lockfiles. The Arch-owned Bun executable remains a `paru` concern. |
| Zim framework and modules | Zim step | Runs `zimfw upgrade && zimfw update` in interactive zsh. [Source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/zsh.rs) |
| LazyVim plugins and Mason packages | Vim step | Runs headless Neovim updates, including `:MasonUpdate` and `:Lazy! sync`. [Updater source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/upgrade.vim) |
| Rust toolchains and Cargo-installed binaries | Rustup and Cargo steps | Rustup updates managed toolchains but self-updates only when installed standalone. Keep Topgrade's Cargo `git = true` behavior so the installed `cargo-install-update` receives both `--git` and `--all`; without `--git`, Git-installed binaries are excluded. [Configuration](https://github.com/topgrade-rs/topgrade/blob/main/config.example.toml) |
| Flatpaks | Flatpak step | Updates user and system installations. [Flatpak docs](https://docs.flatpak.org/en/latest/using-flatpak.html) |
| Go-installed binaries | Go step | Uses installed `gup update`. [Configuration](https://github.com/topgrade-rs/topgrade/blob/main/config.example.toml) |
| Agent skills | Skills step | Uses the Skills CLI global update mode. Keep this interactive: upstream has active reports of incorrect or overly broad updates. [Skills CLI](https://github.com/vercel-labs/skills#skills-update) · [upstream issue](https://github.com/vercel-labs/skills/issues/923) |

Topgrade added the native Skills step in version 17.1.0; install the current AUR package, not an old binary. [Topgrade changelog](https://github.com/topgrade-rs/topgrade/blob/main/CHANGELOG.md)

## Docker service deployment

Keep package upgrades and service deployments as separate operations:

- `upgrade` updates packages and development tools through Topgrade.
- `upgrade services` deploys updates only to Compose projects that are currently
  running from `~/Projects/services`. It must not start stopped or previously
  undeployed projects merely because their Compose files exist.

Do **not** enable Topgrade's `containers` step. It pulls tagged local images but
does not recreate or restart Compose containers, so it can consume bandwidth
without deploying an update.
[Container step source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/containers.rs)

`upgrade services` delegates to
`$(xdg-user-dir PROJECTS)/services/services.sh update`. That script owns service
discovery and deployment: it snapshots the running Compose services under its
repository, preserves each project's active Compose and override files, pulls
registry images, rebuilds build-backed services with fresh base images, and
recreates only the services in the snapshot. Do not duplicate that lifecycle in
the `upgrade` launcher.

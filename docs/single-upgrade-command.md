# Single upgrade command

## Decision

Use **[Topgrade](https://github.com/topgrade-rs/topgrade)** as the interactive orchestrator and expose it as an `upgrade` command that executes `topgrade`.

Install Topgrade through the host package manager. On this Arch host, use `paru`; it is the package helper the dotfiles bootstrap and install helpers already own. The task note was written on **March 10, 2026**, but the current setup on **July 17, 2026** has both helpers installed and is configured around `paru`. Pin Topgrade to `paru` rather than depending on auto-detection.

Do not make package upgrades unattended and do not default to `--yes`. AUR builds, pacnew review, and runtime/service changes need a human present.

## Managed Topgrade policy

```toml
# ~/.config/topgrade.toml
[misc]
# The package manager, not Topgrade's standalone updater, owns this executable.
no_self_update = true
disable = ["containers"]

[linux]
arch_package_manager = "paru"

[git]
# Dotman is the configuration source of truth; upgrades must not git-pull managed config.
pull_predefined = false
```

Topgrade's default Git step considers paths such as `~/.config/nvim` and shell configuration repositories. Disable predefined Git pulls so the `upgrade` command cannot bypass the dotman workflow. Topgrade supports an explicit Arch helper, supports `no_self_update`, and provides this Git policy in its configuration/source. [Topgrade configuration](https://github.com/topgrade-rs/topgrade/blob/main/config.example.toml) · [Git step source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/git.rs)

## Coverage

| Concern | Owner / Topgrade step | Notes |
| --- | --- | --- |
| Arch repos, AUR, and Arch-owned executables (`uv`, `bun`, `nvim`, Docker) | `paru` system step | Runs the normal full Arch/AUR upgrade. |
| Homebrew on the macOS profile | Brew steps | Automatically used only where `brew` exists. |
| uv tools and uv-managed Pythons | `Uv` | Updates tools; attempts `uv self update` only when self-updates are supported, so the Arch-owned `/usr/bin/uv` remains owned by `paru`. [uv tools](https://docs.astral.sh/uv/concepts/tools/) · [Topgrade uv step](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/generic.rs) |
| npm and Bun global packages | npm and Bun-package steps | The current user-owned npm prefix is compatible with this. The Arch-owned Bun executable remains a `paru` concern. |
| Zim framework and modules | Zim step | Runs `zimfw upgrade && zimfw update` in interactive zsh. [Source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/zsh.rs) |
| LazyVim plugins and Mason packages | Vim step | Runs headless Neovim updates, including `:MasonUpdate` and `:Lazy! sync`. [Updater source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/upgrade.vim) |
| Rust toolchains and Cargo-installed binaries | Rustup and Cargo steps | Cargo uses the installed `cargo-install-update`, including Git-origin packages by default. [Configuration](https://github.com/topgrade-rs/topgrade/blob/main/config.example.toml) |
| Flatpaks | Flatpak step | Updates user and system installations. [Flatpak docs](https://docs.flatpak.org/en/latest/using-flatpak.html) |
| Go-installed binaries | Go step | Uses installed `gup update`. [Configuration](https://github.com/topgrade-rs/topgrade/blob/main/config.example.toml) |
| Agent skills | Skills step | Uses the Skills CLI global update mode. Keep this interactive: upstream has active reports of incorrect or overly broad updates. [Skills CLI](https://github.com/vercel-labs/skills#skills-update) · [upstream issue](https://github.com/vercel-labs/skills/issues/923) |

Topgrade added the native Skills step in version 17.1.0; install the current AUR package, not an old binary. [Topgrade changelog](https://github.com/topgrade-rs/topgrade/blob/main/CHANGELOG.md)

## Docker limit

Do **not** enable Topgrade's `containers` step by default. It pulls tagged local images but does not recreate or restart Compose containers, so it can consume bandwidth without deploying an update. Each deployed Compose application needs an explicit, reviewed deployment command (typically `docker compose pull` followed by its own `docker compose up -d`) before it belongs in the upgrade flow. [Container step source](https://github.com/topgrade-rs/topgrade/blob/main/src/steps/containers.rs)

## Periodic check

Use a **systemd user timer** for a non-mutating checker and desktop notification, not for `upgrade` itself. The timer should report pending Arch, Flatpak, and Homebrew updates where available; `checkupdates` safely uses its own temporary pacman database. [`checkupdates(8)`](https://man.archlinux.org/man/extra/pacman-contrib/checkupdates.8.en) · [`systemd.timer(5)`](https://www.freedesktop.org/software/systemd/man/systemd.timer.html)

Implement the checker separately after choosing its notification UX. It must never call `topgrade`, `paru -Syu`, or `--yes`.

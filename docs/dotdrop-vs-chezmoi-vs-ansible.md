# Why This Repo Uses Dotdrop Instead Of Chezmoi Or Ansible

This repo is optimized for editing real files on a machine, then pulling those
changes back into version control cleanly. That requirement matters more here
than remote orchestration, secret management, or a large provisioning feature
set.

The short version: `dotdrop` is the best fit because its reverse-sync workflow
is the most direct, and `trans_update` makes that workflow practical even for
machine-generated formats that need normalization before they are committed.

## Decision Summary

If the main loop is:

1. install config to the machine
2. tweak the live file in place
3. sync the result back into the repo
4. normalize generated noise before commit

then `dotdrop` is the cleanest tool of the three.

`chezmoi` is strong for home-directory dotfiles, templating, and secrets, but
its model is centered on a destination directory that is usually `~`, and its
reverse-sync path is weaker for templates and non-file targets.

`ansible` is excellent for provisioning and remote automation, but reverse sync
is not a first-class workflow. You end up composing `fetch`, `synchronize`, and
privilege handling yourself.

## Comparison

| Tool | What it is best at | Reverse sync | System files | Fit for this repo |
| --- | --- | --- | --- | --- |
| `dotdrop` | Dotfile deployment with explicit source/destination mapping | Best of the three: built-in `update`, plus `trans_update` for write-side normalization | Usable, but mixed user/root flows need care | Best fit |
| `chezmoi` | Home-directory dotfiles, templating, secrets, machine-specific state | Good for simple files via `add`/`re-add`, weaker for templates and non-file entries | Possible, but usually via scripts or staging tricks | Acceptable, but more awkward |
| `ansible` | Provisioning, remote automation, declarative system changes | Weakest: reverse sync is assembled from modules | Strong | Useful companion tool, not the main dotfile tool |

## Why Dotdrop Wins Here

### 1. Reverse sync is a first-class workflow

`dotdrop` has an explicit `update` command that copies changes from the live
filesystem back into the repo. That matches the way this repo is maintained:
real config files are often edited and validated in place first.

The important part is not just `update`, but `trans_update`. `trans_update`
lets the repo transform live files before they are written back into the
managed source tree. That is exactly what makes reverse sync reliable for
formats that include unstable ordering, generated noise, or machine-local data.

This repo already uses that pattern in `config.yaml`, for example:

- `toml_strip_keys`
- `xml_sort_attr_rm_nodes`
- `plist_to_xml_compare`
- `globalpreferences_to_xml`

Without write-side transforms, reverse sync is much noisier and often too
fragile to use comfortably.

### 2. Arbitrary path mapping is natural

This repo manages both home-directory files and system paths such as `/etc`.
`dotdrop` models dotfiles as explicit source-to-destination mappings, which is
a better fit for that than a home-directory-first tool.

That does not mean stock `dotdrop` is perfect for mixed privilege handling.
Its own docs recommend care here and suggest separating user and root-managed
configs. In this repo, [`dotfiles/bin/dotdrop-sudo`](../dotfiles/bin/dotdrop-sudo)
is the local wrapper that smooths over that operational gap.

Even with that caveat, `dotdrop` still fits the repo better because the core
workflow remains "map a path, install it, compare it, update it back."

### 3. Compare and update are aligned

`dotdrop` keeps `install`, `compare`, and `update` in one model. The same
managed entry can be deployed, diffed, and pulled back. That keeps the day to
day workflow simple.

## Why Not Chezmoi

`chezmoi` is a strong tool, but it is not the best match for this repo's
priorities.

### Reverse sync is weaker than dotdrop's

`chezmoi` supports reverse sync through `add` and `re-add`, but the official
docs say `re-add` only re-adds modified files, ignores non-file entries, and
does not overwrite templates. That is workable, but it is not as strong as
`dotdrop update` plus `trans_update`.

For a repo that wants to round-trip generated config formats through cleanup
transforms, `chezmoi` is noticeably less direct.

### System files are outside its natural center of gravity

Officially, `chezmoi` manages a destination directory that is usually `~`.
That is a good fit for user dotfiles, but less natural for `/etc` and other
root-owned paths.

There is a workaround, and it is a reasonable one: stage system files under the
chezmoi source tree, then use `run_` or `run_onchange_` scripts to copy them
into privileged locations with `sudo`. That is conceptually similar to how this
repo uses `dotdrop-sudo` to handle privileged operations.

The difference is where the workaround lives:

- with `dotdrop`, reverse sync and path mapping remain core features, and the
  wrapper mainly handles privilege boundaries
- with `chezmoi`, the system-file story is more script-driven, and the docs
  explicitly note that scripts break the declarative model and should be used
  sparingly

So yes, `chezmoi` can be made to work for system files, but it feels more like
an adaptation than the native shape of the tool.

## Why Not Ansible

`ansible` is the right tool when the primary job is provisioning machines,
managing fleets, or applying system state across hosts. That is not the main
problem this repo is solving.

For reverse sync, `ansible` is the least ergonomic choice here:

- `ansible.builtin.fetch` works in reverse to `copy`, but only for files
- directory pullback usually means `ansible.posix.synchronize` in `pull` mode
- you still need to design your own local repo layout and privilege workflow

That is powerful, but too much ceremony for "edit local config, sync it back,
normalize it, commit it."

`ansible` still makes sense as a companion provisioning tool. It is just not
the best primary tool for this repo's dotfile round-trip workflow.

## Watch Mode

I could not find a built-in watch mode in the official `dotdrop` docs. The
documented commands are `import`, `install`, `compare`, `files`, `update`,
`remove`, `uninstall`, and `gencfg`, and `-w/--workers` refers to concurrency,
not filesystem watching.

So the practical answer is: no built-in watch mode.

If watch behavior is needed, it should be layered on top with an external file
watcher such as:

- `watchexec`
- `entr`
- a `systemd --user` path unit
- a small wrapper script that runs `dotdrop compare` or `dotdrop update`

For contrast, `chezmoi` documents a Watchman-based workflow, but that is also
an external watcher rather than a native built-in watch command.

## Bottom Line

`dotdrop` is the chosen tool here because it has the best reverse-sync story.
The combination of explicit path mapping, built-in `update`, and write-side
transforms through `trans_update` matches the maintenance style of this repo
better than either `chezmoi` or `ansible`.

`chezmoi` is attractive for home-directory management, but weaker for this
repo's mix of reverse sync, transforms, and system-file handling.

`ansible` is stronger for provisioning than for day-to-day dotfile round trips.

## References

- `dotdrop` usage: <https://dotdrop.readthedocs.io/en/latest/usage/>
- `dotdrop` transformations: <https://dotdrop.readthedocs.io/en/latest/config/config-transformations/>
- `dotdrop` system dotfiles: <https://dotdrop.readthedocs.io/en/latest/howto/system-config-files/>
- `chezmoi` concepts: <https://www.chezmoi.io/reference/concepts/>
- `chezmoi re-add`: <https://www.chezmoi.io/reference/commands/re-add/>
- `chezmoi` scripts: <https://www.chezmoi.io/user-guide/use-scripts-to-perform-actions/>
- `chezmoi` with Watchman: <https://www.chezmoi.io/user-guide/advanced/use-chezmoi-with-watchman/>
- `ansible.builtin.fetch`: <https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/fetch_module.html>
- `ansible.posix.synchronize`: <https://docs.ansible.com/projects/ansible/latest/collections/ansible/posix/synchronize_module.html>

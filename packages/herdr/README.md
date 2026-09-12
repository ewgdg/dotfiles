# Herdr

This package manages Herdr, reviewr, and the
[herdr-nvim](https://github.com/jtnovellis/herdr-nvim) integration.

## Neovim sidebar and file links

The `nvim_installed` probe installs herdr-nvim v0.2.3 when the plugin is
missing or disabled. An enabled installation is left alone; this is not an
automatic update check. Herdr runs the plugin's build step, which verifies a
release download's SHA-256 or builds with Cargo when no matching binary exists.
Requirements: Herdr 0.8.2+, Neovim 0.11+, and Rust 1.82+ for source builds.
Neovim itself is provided by the separate `nvim` package.

The sidebar loads the plugin's bundled Lua alongside the normal Neovim config.
No duplicate lazy.nvim installation is needed for sidebar use.

| Input | Action |
| --- | --- |
| Ctrl-click an OSC8 `file://` hyperlink | Open the file in the tab's Neovim sidebar |
| `prefix+e` | Focus the sidebar, or hide it when already focused |
| `prefix+f` | Pick a file from agent output or the repository |
| `prefix+shift+e` | Edit pane scrollback |

`prefix` is Herdr's configured prefix key. Plain file text is not necessarily
a hyperlink. Shift-Ctrl-click uses the outer terminal's opener instead and
does not use this plugin. No `xdg-open` or MIME association changes are needed
for the Herdr plugin route.

The sidebar uses a per-tab headless Neovim daemon. Hiding it keeps buffers alive;
closing the tab saves modified buffers before stopping the daemon by default.
Inside the sidebar, `:q` detaches and `:qa` quits the daemon.

## Install and maintain

Run the normal user-driven `dotman push herdr` to apply the package. For an
immediate native plugin installation without syncing other Herdr configuration:

```sh
herdr plugin install jtnovellis/herdr-nvim --ref v0.2.3 --yes
herdr plugin action invoke setup-keys --plugin herdr-nvim
```

The upstream `setup-keys` action backs up the live config, preserves conflicting
bindings, and reloads it. The same bindings are tracked in this package; normal
dotman pushes do not need that action.

For an update, choose a reviewed release, update the hook's `--ref`, and run
the corresponding native install command explicitly. The missing-only probe
will not update an already enabled plugin. Restart existing sidebar daemons
after saving their buffers so the new bundled Lua is loaded.

Checks:

```sh
herdr config check
herdr plugin list
herdr plugin action list --plugin herdr-nvim
herdr plugin log list --plugin herdr-nvim
```

Within the sidebar, use `:checkhealth herdr-nvim` for integration diagnostics.

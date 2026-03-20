# Dotdrop State Marker Actions

Use this pattern when you want `dotdrop` to trigger setup work without managing
a real config payload. Instead of copying an actual app config, manage a small
marker file under the current `XDG_STATE_HOME`, typically
`~/.local/state/dotdrop/`, and attach the setup action to that dotfile entry.

This repo's current example is `f_local_state_dotdrop_rustup-installed` in
`config.yaml`.

## Example

```yaml
f_local_state_dotdrop_rustup-installed:
  src: local/state/dotdrop/rustup-installed
  dst: ~/.local/state/dotdrop/rustup-installed
  actions:
    - sh '{{@@ _dotdrop_dotpath @@}}/../scripts/install_rustup.sh'
```

The source file at `dotfiles/local/state/dotdrop/rustup-installed` is empty.
Its only job is to give `dotdrop` a harmless target to manage. The real work
happens in `scripts/install_rustup.sh`.

The profile then includes that key like any other dotfile:

```yaml
toolchain_rust:
  dotfiles:
    - f_local_state_dotdrop_rustup-installed
```

## When To Use It

Use a state-marker entry when:

- you need `dotdrop install` to trigger an installer or bootstrap step
- there is no meaningful config file to deploy
- you want the state recorded under the current `XDG_STATE_HOME` instead of
  inventing a fake config

In this repo, `~/.local/state` is the default because `dotfiles/profile`
exports `XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"`. If a machine
uses a different `XDG_STATE_HOME`, treat that as the canonical base for the
marker path.

Do not use it when you actually need to manage a real file. In that case, model
the real file directly in `config.yaml`.

## Important Constraint

This pattern does not replace idempotency checks in the action itself.

Treat the marker file as a trigger and a small piece of local state, not as a
strict guarantee that the action can never run again. The action script must be
safe to rerun and should exit successfully when the target is already set up.

The `rustup` example does that by checking `command -v rustup` first and
skipping the installer when `rustup` is already available.

## Recommended Pattern

When adding a new one-time setup action:

1. Create an empty marker file under `dotfiles/local/state/dotdrop/`.
2. Add a dotdrop entry whose `dst` lives under the active `XDG_STATE_HOME`,
   usually `~/.local/state/dotdrop/`.
3. Attach an idempotent action script to that entry.
4. Include the entry in the profile that should perform the setup.

Name the marker file for the condition it represents, for example
`example-tool-installed`.

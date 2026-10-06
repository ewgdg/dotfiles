# fnm

Installs [fnm](https://github.com/Schniz/fnm) for project-local node versions.
No group selects it; track it on a host that needs a pinned node.

The system node from `packages/nodejs` stays the ambient runtime. fnm cannot be
told to leave new shells alone: `fnm env` links each shell to the `default`
alias, and `fnm install` creates that alias from the first version installed
([Schniz/fnm#1419](https://github.com/Schniz/fnm/issues/1419)). So
`packages/shell`'s `fnm.zsh` runs `fnm use system` right after `fnm env`, and the
alias no longer decides anything. `fnm use <version>` still switches a project
shell.

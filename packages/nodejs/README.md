# Node.js

Installs the OS node toolchain, pnpm, bun, and fnm, and tracks `~/.npmrc`.

## Who owns node

The **system node** is the ambient runtime: the OS package named in
`NODEJS_INSTALL_PACKAGES` (`nodejs` on Arch). It also owns the shared global npm
prefix, since `~/.npmrc` sets `prefix=${HOME}/.npm` for every node on the machine.

**fnm is kept for project-local versions only.** Its `default` alias is what makes
it the ambient runtime, so `fnm_default_alias_removed` removes the alias and leaves
the installed version alone: a tree nothing points at is inert, and a project
pinning that version keeps it. `fnm env` then leaves each shell's multishell link
dangling, node resolution falls through to `/usr/bin/node`, and `fnm use` still
repoints the link for a project that needs a different version.

## Node ABI and the global prefix

Native bindings are compiled for one node ABI (`NODE_MODULE_VERSION`), and the
global prefix is shared by every node here, so the node that installs a package
and the node that runs it must agree. Moving the system node to another major version
invalidates all of them at once — `better-sqlite3` and `node-pty` among them.

`npm_globals_match_node_abi` compares the running node's ABI with the one recorded
in `~/.local/state/dotfiles/nodejs/npm-globals-abi` and runs `npm rebuild -g` when
they differ, recording the new ABI only after a successful rebuild so a failure
retries on the next push.

The stamp records what the rebuild did rather than loading an installed module to
see whether it works: a load test fails for reasons unrelated to the ABI, and a
probe that never reports "current" would rebuild on every push.

Two gaps to know about:

- A pacman upgrade outside a push leaves the tree stale until the next push. A
  pacman hook would close that window and is deliberately not used.
- Installing globals from a project shell that has an fnm version active writes
  to the same shared prefix with that version's ABI, mixing bindings in one tree.
  The stamp cannot see that, because it records the rebuild, not the tree. Install
  global packages from a normal shell.

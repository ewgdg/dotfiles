# Node.js

Installs the OS node toolchain, pnpm, bun, and fnm, and tracks `~/.npmrc`.

## fnm default node

Installing the fnm binary does not install a node version or a default alias, so
the `fnm_default_node_on_lts` target keeps the `default` alias on the current
LTS. That alias is the single place node is chosen on this host: interactive
shells resolve it through `fnm env`, global CLIs are installed with its `npm`,
and `packages/linux/devspace` starts its service through
`fnm exec --using=default`.

The probe resolves the latest LTS and compares it with the installed default, so
a push installs a newer LTS when one exists. When the network is unavailable the
probe keeps the installed default instead of forcing churn.

## One node tree at a time

Each fnm node tree is roughly 200 MB, and a newer LTS — including a patch release
— installs a new one, so the replaced tree is removed in the same run.

That is safe because of how fnm wires shells up. `fnm env` points each shell's
multishell link at the `default` alias, not at a version tree:

```text
shell link -> aliases/default -> node-versions/<version>/installation
```

So `fnm default` moves every live shell at once, and once the alias has moved,
nothing references the replaced tree and it can be removed. The script relies on
that indirection and must not relink shell links itself: pointing a shell link
directly at a version tree severs the alias hop, and that shell then stops
following later `fnm default` moves.

The order in the script is load-bearing: `fnm uninstall` also removes the aliases
that point at the version, so the default alias has to move first. If fnm refuses
the removal, the script reports it and leaves the tree in place.

## Node majors and native modules

A native module is built for the ABI of one node major, so the node that installs
a package and the node that runs it must agree. When a new LTS crosses a major,
the target rebuilds the global packages in the same run:

```sh
fnm exec --using=default -- npm rebuild -g
```

That step matters because the global CLIs here carry native bindings: `node-pty`,
`@earendil-works/pi-coding-agent`, `@deepseek-ai/dsh`, `@koromix`, `@img`, and
devspace's `better-sqlite3`. Without the rebuild they fail to load with a
`NODE_MODULE_VERSION` mismatch. After any manual node change, run the same
command.

The devspace runtime accepts `>=20.12 <27`, so the current LTS (24) and the next
one (26) are inside that range; an LTS line beyond it needs a devspace release
that widens the range before the service would start.

# Node.js

Installs the OS node toolchain, pnpm, bun, and fnm, and tracks `~/.npmrc`.

## fnm default node

Installing the fnm binary does not install a node version or a default alias, so
the `fnm_default_node_installed` target installs the latest LTS and points the
`default` alias at it. The probe asks fnm for a node through that alias rather
than inspecting fnm's on-disk layout, because the alias is what consumers
actually resolve.

`packages/linux/devspace` depends on it: the service starts through
`fnm exec --using=default`. That coupling is deliberate. A native module such as
devspace's `better-sqlite3` is built for the ABI of the node that ran `npm`, so
the node that installs a package and the node that runs it must be the same
major. Changing this default later means rebuilding affected native modules:

```sh
npm rebuild -g better-sqlite3
```

The LTS version is resolved when the target acts, so a host that already has a
working default keeps it: the target only runs when the alias is missing or
unusable.

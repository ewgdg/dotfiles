# Niri

## Custom Arch package

This package uses a custom Git build of niri. `dotman push niri` builds and installs it automatically.

Manual install from the repo root:

```bash
paru --keepsrc -Bi packages/niri/packaging/arch/niri-custom-git
```

The package is named `niri-custom-git` and provides/conflicts with `niri`, so pacman tracks it separately from the official repo package.

This private package intentionally does not track `.SRCINFO`; `PKGBUILD` is the source of truth.

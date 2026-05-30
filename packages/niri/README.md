# Niri

## Custom Arch package

This package uses a custom Git build of niri. `dotman push niri` builds and installs it automatically.

Manual install from the repo root, using the same cache staging as `dotman push`:

```bash
sh scripts/install_arch_custom_package.sh --keepsrc packages/niri/packaging/arch/niri-custom-git
```

The package is named `niri-custom-git` and provides/conflicts with `niri`, so pacman tracks it separately from the official repo package.

The wrapper keeps makepkg state under `${XDG_CACHE_HOME:-~/.cache}/makepkg/local/`: PKGBUILD staging in `pkgbuilds/niri-custom-git/`, build work under `builds/`, downloaded/VCS sources in `sources/niri-custom-git/`, built packages in `packages/`, source packages in `source-packages/`, and logs in `logs/niri-custom-git/`. Package-local `.gitignore` rules keep makepkg artifacts out of staging.

This private package intentionally does not track `.SRCINFO`; `PKGBUILD` is the source of truth.

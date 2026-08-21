# Niri custom Git package

This dotman package owns the private Arch `niri-custom-git` build. The package
provides and conflicts with `niri`, so pacman tracks it separately from the
official repository package.

`dotman push niri-custom-git` compares the installed Git hash with upstream
`HEAD`. It builds and installs the PKGBUILD when the package is missing,
upstream has advanced, or the histories have diverged. An installed commit
that is ahead of upstream is kept.

Topgrade loads the package's `~/.config/topgrade.d/niri-custom-git.toml` and
runs `dotman push --yes niri-custom-git` as **Niri custom build**. The `--yes`
flag skips dotman's confirmation prompt, and the narrow selector does not push
the Niri configuration package. Package installation can still request `sudo`
authentication.

For a manual build from the repository root:

```bash
sh scripts/install_arch_custom_package.sh --keepsrc packages/niri-custom-git/packaging/arch/niri-custom-git
```

The wrapper keeps makepkg state under
`${XDG_CACHE_HOME:-~/.cache}/makepkg/local/`: PKGBUILD staging in
`pkgbuilds/niri-custom-git/`, build work under `builds/`, downloaded/VCS
sources in `sources/niri-custom-git/`, built packages in `packages/`, source
packages in `source-packages/`, and logs in `logs/niri-custom-git/`.
Package-local `.gitignore` rules keep makepkg artifacts out of staging.

This private package intentionally does not track `.SRCINFO`; `PKGBUILD` is the
source of truth.

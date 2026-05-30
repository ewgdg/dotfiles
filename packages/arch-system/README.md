# Arch system

Owns Arch package-manager configuration and the repo bootstrap path for `paru`.

`pre_push` runs `scripts/install_paru.sh` before syncing pacman/paru config. The shared Arch install helpers also call that script when `paru` is missing, so package hooks using `{{ INSTALL }}` can self-bootstrap on a fresh Arch host.

Override knobs, mainly for testing or recovery:

- `PARU_AUR_PACKAGE` — AUR package to clone/build; default `paru-bin`
- `PARU_AUR_GIT_URL` — clone URL; default derives from package name
- `PARU_AUR_SOURCE_DIR` — checkout/build directory; default under XDG cache

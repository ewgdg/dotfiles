# Move node ownership to pacman, keep fnm for project versions

## Goal

The system node (an Arch LTS package) owns the ambient runtime and the shared
global npm prefix. fnm is demoted to project-local versions only. Nothing in the
repo tracks "the current LTS" any more.

## Intention

Today fnm's `default` alias is the machine's node: it is the runtime for
interactive shells, for the shared `~/.npm` globals, and for the devspace
service. That works, but it means node is installed by a version manager and
upgraded by a hand-written script, while pacman ships a second node that nothing
uses. The repo's own rule — the package manager that installed an executable is
its sole upgrade owner — points the other way.

Two facts make the alternative cheap:

- Arch keeps every LTS line as its own package (`nodejs-lts-iron/jod/krypton`),
  so a line move is a deliberate `pacman -S nodejs-lts-<next>`, never a
  surprise.
- `fnm env` works with no default alias at all: the multishell link simply
  dangles and node resolution falls through to `/usr/bin/node`. Verified.

## Scope & Constraints

In scope:

- Arch profile installs `nodejs-lts-krypton` instead of `nodejs`.
- Drop fnm's `default` alias (it shadows the system node in every shell) and
  the tree it was pointing at.
- Rebuild global native modules when the node ABI changes, detected on push.
- devspace service runs the inherited system node; no `fnm exec`.

Out of scope:

- macOS profile (still `node` from Homebrew).
- Per-runtime npm prefixes. Installing globals from a project shell that has an
  fnm version active can still mix ABIs in one tree; recorded as a follow-up.
- A pacman hook for the ABI rebuild. The push-time probe is the accepted
  latency; a hook would remove it.

## Work Plan

1. `profiles/os/arch.toml`: `NODEJS_INSTALL_PACKAGES = "nodejs-lts-krypton npm
   pnpm"`.
2. `packages/nodejs/scripts/fnm_default_alias_removed.sh` (probe|apply): probe
   exits 0 while `fnm default` reports a version; apply removes the alias only,
   leaving the version tree for any project that pins it.
3. `packages/nodejs/scripts/npm_globals_abi.sh` (probe|apply): compares
   `process.versions.modules` with the ABI recorded in
   `~/.local/state/dotfiles/nodejs/npm-globals-abi`; apply runs
   `npm rebuild -g` and records the current ABI.
4. `packages/nodejs/package.toml`: replace the LTS tracker target with the two
   above, ordered after the install target so the rebuild runs under the new node.
5. Delete `scripts/fnm_default_lts.sh` and rewrite `packages/nodejs/README.md`.
6. `packages/linux/devspace`: unit runs `%h/.npm/bin/devspace serve`;
   `depends` gains `nodejs` so the runtime and globals are settled first.
7. Tests: rewrite `tests/test_nodejs_package.py` for both scripts; update the
   devspace unit assertions.

## Validation

- Stub tests for both scripts: alias present/absent, ABI match/mismatch, node
  missing, network-free.
- `dotman push nodejs -d` shows install before rebuild.
- Manual, on push: `pacman -Q nodejs-lts-krypton`, `fnm default` errors,
  `command -v node` is `/usr/bin/node`, `systemctl --user status devspace`.
- paru resolves the `nodejs` conflict unattended through the existing
  `--useask` flag; if it does not, run `pacman -S nodejs-lts-krypton` by hand
  and re-push.

## Progress

- [x] Plan written.
- [x] Arch profile names `nodejs-lts-krypton`; the LTS tracker and its script are
      gone.
- [x] Both scripts implemented, with stub tests covering alias present/absent,
      ABI match/mismatch, a failing rebuild, and a missing node.
- [x] devspace unit runs the inherited system node and depends on `nodejs`.
- [x] `dotman push nodejs -d` plans install → alias removal → ABI rebuild in that
      order, and `dotman push linux/devspace -d` plans nodejs first.
- [ ] First real push: confirm paru resolves the `nodejs` conflict unattended,
      then that `node` is `/usr/bin/node` and devspace serves.

## Validation Results

- Touched test files: 14 passed.
- Whole suite after the change: 25 failed, 202 passed, 1 skipped.
- Baseline at the pre-change commit, same interpreter and sibling worktree
  location: 25 failed, 198 passed, 1 skipped — the same 25 failures by file
  (`json/plist/toml/goldendict manifest migration`, `journal_create`, `init`,
  `faugus_launcher_config`, `dotman_catalog`), all from the pre-existing
  `gitignore must be a boolean, got list` mismatch between this repo and the
  dotman checkout. The extra four passes are the tests added here.

## Decisions

- System node is the LTS package, not Arch's `nodejs`: devspace asserts
  `>=20.12 <27`, and Arch's current line reaches 27 on pacman's schedule with no
  supported way to hold it back.
- ABI, not version string, is the rebuild trigger: it is the invariant native
  bindings actually depend on.
- Rebuild state is a stamp file recording the ABI the tree was last rebuilt for,
  rather than a load test of installed modules: a load test can fail for reasons
  unrelated to the ABI, and a probe that never returns 100 would rebuild on every
  push.
- fnm keeps its place for project versions; only the `default` alias goes away.
- The alias is removed, not the version tree. The alias is what fnm env points
  shells at, and an unaliased tree is inert; uninstalling it would only force a
  200 MB re-download for a project that pins that version.
- The devspace service is not restarted when node changes. Verified: `fnm exec`
  puts the alias bin on PATH, but with the system node the service simply
  inherits it, and children resolve through the same runtime. A stale runtime
  only matters for lazily imported native bindings, and the remedy is
  `systemctl --user restart devspace`.

## Surprises & Discoveries

- `fnm env` emits a multishell PATH entry even with no default alias, and the
  dangling link is harmless: node resolution falls through to the next PATH
  entry. This is what makes "fnm for projects only" work without touching the
  shell plugin's activation model.
- `readlink -f` on a multishell link cannot distinguish "points at a version
  tree" from "points at the alias that points at the tree", which produced a
  wrong conclusion earlier in this work; `readlink` alone shows the alias hop.

## Outcomes & Retrospective

Pending implementation and a real push.

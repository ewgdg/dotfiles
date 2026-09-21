#!/bin/sh
# Keeps fnm's default node on the current LTS line. That default is the runtime
# for interactive shells, globally installed CLIs, and the devspace service, so
# it is the single place node is chosen on this host.
#
# Native modules are built for the ABI of exactly one node major, so crossing a
# major rebuilds the global packages in the same run. Without that step, pi,
# devspace, dsh, and codex would fail to load their native bindings.
set -eu

action="${1:-}"
case "${action}" in
  probe|apply) ;;
  *)
    echo "usage: fnm_default_lts.sh probe|apply" >&2
    exit 2
    ;;
esac

latest="$(fnm ls-remote --lts --latest 2>/dev/null | cut -d" " -f1 || true)"
current="$(fnm exec --using=default -- node --version 2>/dev/null || true)"

if [ -z "${latest}" ]; then
  # Keep the installed default rather than forcing churn when the network is out.
  echo "could not resolve the latest LTS; keeping ${current:-the installed default}" >&2
  exit 100
fi

if [ "${current}" = "${latest}" ]; then
  exit 100
fi

if [ "${action}" = "probe" ]; then
  echo "fnm default is ${current:-unset}, latest LTS is ${latest}" >&2
  exit 0
fi

# Directory of the fnm tree currently backing the default alias. Fails rather than
# returning a partial path, because a bad value here would repoint live shell
# links at something meaningless.
node_dir() {
  exec_path="$(fnm exec --using=default -- node -e 'process.stdout.write(process.execPath)' 2>/dev/null || true)"
  resolved="$(readlink -f "${exec_path}" 2>/dev/null || true)"
  case "${resolved}" in
    */bin/node) dirname "$(dirname "${resolved}")" ;;
    *) return 1 ;;
  esac
}

previous_dir="$(node_dir || true)"
previous_major="${current%%.*}"
fnm install "${latest}"
fnm default "${latest}"
current_major="$(fnm exec --using=default -- node --version | cut -d. -f1)"

if [ "${previous_major}" != "${current_major}" ]; then
  echo "node major ${previous_major:-none} -> ${current_major}: rebuilding global native modules" >&2
  fnm exec --using=default -- npm rebuild -g
fi

# Keep one node tree per LTS line. Each tree is roughly 200 MB, so a move that
# leaves the old one behind accumulates fast. Live shells resolve node through
# their own fnm multishell link, which points into the tree being removed. fnm
# only repoints the link of the shell it runs in, so uninstalling leaves every
# other shell dangling; those links are repointed here before the removal.
new_dir="$(node_dir || true)"

if [ -d "${previous_dir}" ] && [ -d "${new_dir}" ] && [ "${previous_dir}" != "${new_dir}" ]; then
  multishell_root="${FNM_MULTISHELL_ROOT:-${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/fnm_multishells}"
  for link in "${multishell_root}"/*; do
    [ -L "${link}" ] || continue
    [ "$(readlink -f "${link}")" = "${previous_dir}" ] || continue
    ln -sfn "${new_dir}" "${link}"
    echo "repointed ${link} to ${new_dir}" >&2
  done

  # Order matters: fnm uninstall also removes the aliases that point at the
  # version, so the default alias must already point at the new tree (set above).
  if fnm uninstall "${current}" >/dev/null 2>&1; then
    echo "removed the replaced node ${current}" >&2
  else
    echo "kept the replaced node ${current}: fnm could not remove it" >&2
  fi
fi

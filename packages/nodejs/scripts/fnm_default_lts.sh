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

previous_major="${current%%.*}"
fnm install "${latest}"
fnm default "${latest}"
current_major="$(fnm exec --using=default -- node --version | cut -d. -f1)"

if [ "${previous_major}" != "${current_major}" ]; then
  echo "node major ${previous_major:-none} -> ${current_major}: rebuilding global native modules" >&2
  fnm exec --using=default -- npm rebuild -g
fi

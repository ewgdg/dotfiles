#!/bin/sh
# fnm is kept for project-local versions only. Its `default` alias is what makes
# it the ambient runtime: fnm env points each shell's multishell link at that
# alias, so while the alias exists the system node never wins. Removing it leaves
# the link dangling, which is harmless — node resolution falls through to
# /usr/bin/node.
set -eu

action="${1:-}"
case "${action}" in
  probe|apply) ;;
  *)
    echo "usage: fnm_default_alias_removed.sh probe|apply" >&2
    exit 2
    ;;
esac

# Errors when unset, and prints nothing when fnm itself is missing; both mean
# there is no alias to remove, and installing fnm belongs to the install target.
default_version="$(fnm default 2>/dev/null || true)"

if [ -z "${default_version}" ]; then
  echo "fnm has no default alias; the system node is the ambient runtime" >&2
  exit 100
fi

if [ "${action}" = "probe" ]; then
  echo "fnm still defaults to ${default_version}, shadowing the system node" >&2
  exit 0
fi

# The alias is the whole problem: it is what fnm env points shells at. The version
# tree is inert without it, so it stays installed and a project that pins this
# version keeps working. Reclaim its ~200 MB with fnm uninstall only if nothing
# needs it.
fnm unalias default
echo "removed the fnm default alias; ${default_version} stays installed" >&2

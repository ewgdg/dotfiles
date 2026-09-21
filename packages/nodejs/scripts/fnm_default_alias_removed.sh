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

# fnm uninstall also drops the aliases that point at the version, so removing the
# tree is what clears the alias. A project that needs this version again gets it
# back with fnm use --install-if-missing.
if fnm uninstall "${default_version}" >/dev/null 2>&1; then
  echo "removed the fnm default ${default_version} and its alias" >&2
else
  fnm unalias default >/dev/null 2>&1 || true
  echo "removed the fnm default alias; kept the ${default_version} tree" >&2
fi

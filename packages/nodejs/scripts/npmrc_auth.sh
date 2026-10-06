#!/bin/sh
# npm login writes registry credentials into ~/.npmrc as registry-scoped keys
# (`//registry.npmjs.org/:_authToken=...`). They are per-machine secrets, so capture
# drops every `//` line and render carries the live ones over the repo file;
# otherwise a push logs npm out and a pull commits the token.
set -eu

registry_scoped_line='^//'

case "${1:-}" in
  capture)
    grep -v "${registry_scoped_line}" "$2" || true
    ;;
  render)
    grep -v "${registry_scoped_line}" "$2" || true
    # No live file yet on a new machine, so there is no login to keep.
    if [ -e "$3" ]; then
      grep "${registry_scoped_line}" "$3" || true
    fi
    ;;
  *)
    echo "usage: npmrc_auth.sh capture <live> | render <repo> <live>" >&2
    exit 2
    ;;
esac

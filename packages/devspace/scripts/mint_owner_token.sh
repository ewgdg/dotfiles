#!/bin/sh
# DevSpace keeps its OAuth owner password in ~/.devspace/auth.json. That file is a
# live-local secret, so the package never tracks it and this script never prints
# the value: it mints a token only when one is missing. Exit 100 follows the
# dotman probe contract (no action needed).
set -eu

auth_path="${HOME}/.devspace/auth.json"
action="${1:-}"

case "${action}" in
  probe|apply) ;;
  *)
    echo "usage: mint_owner_token.sh probe|apply" >&2
    exit 2
    ;;
esac

if [ -s "${auth_path}" ] && grep -q '"ownerToken"[[:space:]]*:[[:space:]]*"[^"]' "${auth_path}"; then
  exit 100
fi

if [ "${action}" = "probe" ]; then
  exit 0
fi

umask 077
mkdir -p "$(dirname "${auth_path}")"
# 32 random bytes, base64url encoded, matching DevSpace's own generateOwnerToken().
token="$(openssl rand -base64 32 | tr -d '\n' | tr '+/' '-_' | tr -d '=')"
printf '{"ownerToken":"%s"}\n' "${token}" > "${auth_path}"
chmod 600 "${auth_path}"

echo "DevSpace owner password created at ${auth_path}"
echo "Read it when ChatGPT asks for approval: cat ${auth_path}"

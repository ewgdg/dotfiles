#!/bin/sh
# A tunnel cannot run without the credentials cloudflared keeps in ~/.cloudflared: an
# account certificate from `cloudflared tunnel login` and a per-tunnel JSON from
# creating one. Both are interactive or account-level steps this package cannot
# perform, so the probe reports them missing and the apply path fails the push with
# what to run — otherwise the unit restarts every few seconds on an error that reads
# like a network problem. The files are never read for their contents here.
set -eu

action="${1:-}"
case "${action}" in
  probe|apply) ;;
  *)
    echo "usage: check_tunnel_credentials.sh probe|apply" >&2
    exit 2
    ;;
esac

cloudflared_dir="${HOME}/.cloudflared"
missing=""

[ -f "${cloudflared_dir}/cert.pem" ] || missing="${missing} cert.pem"
# Matches the <uuid>.json written when a tunnel is created; an unmatched glob makes
# ls fail, which is what is being tested here.
if ! ls "${cloudflared_dir}"/*.json >/dev/null 2>&1; then
  missing="${missing} <uuid>.json"
fi

if [ -z "${missing}" ]; then
  echo "cloudflared credentials present in ${cloudflared_dir}" >&2
  exit 100
fi

if [ "${action}" = "probe" ]; then
  echo "cloudflared tunnel not ready:${missing}" >&2
  exit 0
fi

cat >&2 <<'EOF'
error: this host has no Cloudflare Tunnel ready to publish DevSpace.

Log in once:
  cloudflared tunnel login

Then create the tunnel, route its DNS to this host, and push again.
EOF
exit 1

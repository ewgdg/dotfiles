#!/bin/sh
# A tunnel cannot run without the credentials cloudflared keeps in ~/.cloudflared:
# an account certificate from `cloudflared tunnel login` and a per-tunnel JSON from
# creating one. Both are interactive or account-level steps this package cannot
# perform, so the probe reports them missing and the apply path fails the push with
# what to run — otherwise the unit restarts every few seconds on an error that reads
# like a network problem.
#
# The tunnel name is passed in because it is host-specific: this package stays
# generic. The files are never read for their contents here.
set -eu

action="${1:-}"
tunnel_name="${2:-}"
case "${action}" in
  probe|apply) ;;
  *)
    echo "usage: check_tunnel_credentials.sh probe|apply <tunnel-name>" >&2
    exit 2
    ;;
esac

cloudflared_dir="${HOME}/.cloudflared"
missing=""

# The unit runs `tunnel run <name>`, so an empty name is its own failure mode.
[ -n "${tunnel_name}" ] || missing="${missing} tunnel-name"
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
error: this host has no Cloudflare Tunnel ready to run.

Log in once:
  cloudflared tunnel login

Then create the tunnel this host should publish, route its DNS, and set
[vars.cloudflared] in the host profile: tunnel_name, hostname, local_service.
EOF
exit 1

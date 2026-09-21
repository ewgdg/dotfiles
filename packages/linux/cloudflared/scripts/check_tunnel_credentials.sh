#!/bin/sh
# cloudflared keeps its account certificate and per-tunnel credentials in
# ~/.cloudflared. Both are live-local secrets produced by commands this package
# cannot run for you, so the probe reports them missing and the apply path fails
# with the commands to run instead of letting the service retry forever on a
# credential error. The files are never read for their contents here.
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
# Matches the <uuid>.json that `cloudflared tunnel create` writes; an unmatched
# glob makes ls fail, which is what is being tested here.
if ! ls "${cloudflared_dir}"/*.json >/dev/null 2>&1; then
  missing="${missing} <uuid>.json"
fi

if [ -z "${missing}" ]; then
  echo "cloudflared credentials present in ${cloudflared_dir}" >&2
  exit 100
fi

if [ "${action}" = "probe" ]; then
  echo "missing cloudflared credentials:${missing}" >&2
  exit 0
fi

cat >&2 <<'EOF'
error: cloudflared credentials are missing, so the tunnel cannot run.
Run these once, then push again:
  cloudflared tunnel login
  cloudflared tunnel create devspace
  cloudflared tunnel route dns devspace devspace.xianzzz.com
EOF
exit 1

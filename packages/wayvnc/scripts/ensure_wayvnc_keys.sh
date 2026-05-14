#!/usr/bin/env bash
set -euo pipefail

config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
wayvnc_dir="$config_home/wayvnc"
tls_key="$wayvnc_dir/tls_key.pem"
tls_cert="$wayvnc_dir/tls_cert.pem"
rsa_key="$wayvnc_dir/rsa_key.pem"

mkdir -p "$wayvnc_dir"

needs_openssl=false
[ -f "$tls_key" ] || needs_openssl=true
[ -f "$tls_cert" ] || needs_openssl=true
[ -f "$rsa_key" ] || needs_openssl=true

if [ "$needs_openssl" = true ] && ! command -v openssl >/dev/null 2>&1; then
  printf 'wayvnc key setup needs command: openssl\n' >&2
  exit 1
fi

umask 077

if [ ! -f "$tls_key" ] && [ ! -f "$tls_cert" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$tls_key" \
    -out "$tls_cert" \
    -days 3650 \
    -subj "/CN=$(hostname)" >/dev/null 2>&1
  chmod 600 "$tls_key"
  chmod 644 "$tls_cert"
elif [ -f "$tls_key" ] && [ ! -f "$tls_cert" ]; then
  openssl req -x509 -key "$tls_key" -new \
    -out "$tls_cert" \
    -days 3650 \
    -subj "/CN=$(hostname)" >/dev/null 2>&1
  chmod 644 "$tls_cert"
elif [ ! -f "$tls_key" ] && [ -f "$tls_cert" ]; then
  printf 'Refusing to generate %s because %s already exists and would not match.\n' "$tls_key" "$tls_cert" >&2
  exit 1
fi

if [ ! -f "$rsa_key" ]; then
  openssl genrsa -traditional -out "$rsa_key" 2048 >/dev/null 2>&1
  chmod 600 "$rsa_key"
fi

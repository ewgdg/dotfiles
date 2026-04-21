#!/usr/bin/env sh
set -eu

managed_begin='# dotman: begin managed core env token'
managed_end='# dotman: end managed core env token'

action=${1:-}
path=${2:-}

usage() {
  cat >&2 <<'EOF'
usage: core_env_token.sh <print|render|capture> <path>

print   Print repo-compatible core env token for file content.
render  Emit deployable env.core.sh with managed token block appended.
capture Emit repo-safe env.core.sh with managed token block stripped.
EOF
}

require_file() {
  if [ -z "${1:-}" ] || [ ! -r "$1" ]; then
    printf '%s\n' "missing readable file: ${1:-}" >&2
    exit 1
  fi
}

count_fixed_line() {
  awk -v needle="$2" '
    $0 == needle { count += 1 }
    END { print count + 0 }
  ' "$1"
}

make_temp_file() {
  mktemp "${TMPDIR:-/tmp}/core-env-token.XXXXXX"
}

strip_managed_block_to_path() {
  input_path=$1
  output_path=$2

  begin_count=$(count_fixed_line "$input_path" "$managed_begin")
  end_count=$(count_fixed_line "$input_path" "$managed_end")
  case "${begin_count}:${end_count}" in
    0:0)
      cat "$input_path" >"$output_path"
      return 0
      ;;
    1:1)
      awk -v begin="$managed_begin" -v end="$managed_end" '
        $0 == begin { in_block = 1; next }
        $0 == end { in_block = 0; next }
        !in_block { print }
      ' "$input_path" >"$output_path"
      return 0
      ;;
    *)
      printf '%s\n' 'mismatched managed core env token block' >&2
      exit 1
      ;;
  esac
}

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{ print $1 }'
    return 0
  fi

  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{ print $1 }'
    return 0
  fi

  if command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | awk '{ print $NF }'
    return 0
  fi

  printf '%s\n' 'no sha256 tool found; need sha256sum, shasum, or openssl' >&2
  exit 1
}

print_token() {
  input_path=$1
  temp_path=$(make_temp_file)
  trap 'rm -f "$temp_path"' EXIT HUP INT TERM
  strip_managed_block_to_path "$input_path" "$temp_path"
  printf 'sha256:%s\n' "$(hash_file "$temp_path")"
  rm -f "$temp_path"
  trap - EXIT HUP INT TERM
}

render_file() {
  input_path=$1
  temp_path=$(make_temp_file)
  trap 'rm -f "$temp_path"' EXIT HUP INT TERM
  strip_managed_block_to_path "$input_path" "$temp_path"
  token=$(printf 'sha256:%s' "$(hash_file "$temp_path")")

  cat "$temp_path"
  if [ -n "$(tail -c 1 "$temp_path" 2>/dev/null || true)" ]; then
    printf '\n'
  fi
  printf '%s\n' "$managed_begin"
  printf '%s\n' "export DOTFILES_ENV_CORE_SH_TOKEN='${token}'"
  printf '%s\n' "$managed_end"

  rm -f "$temp_path"
  trap - EXIT HUP INT TERM
}

capture_file() {
  input_path=$1
  temp_path=$(make_temp_file)
  trap 'rm -f "$temp_path"' EXIT HUP INT TERM
  strip_managed_block_to_path "$input_path" "$temp_path"
  cat "$temp_path"
  rm -f "$temp_path"
  trap - EXIT HUP INT TERM
}

case "$action" in
  print)
    require_file "$path"
    if [ "$#" -ne 2 ]; then
      usage
      exit 2
    fi
    print_token "$path"
    ;;
  render)
    require_file "$path"
    if [ "$#" -ne 2 ]; then
      usage
      exit 2
    fi
    render_file "$path"
    ;;
  capture)
    require_file "$path"
    if [ "$#" -ne 2 ]; then
      usage
      exit 2
    fi
    capture_file "$path"
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage
    exit 2
    ;;
esac

#!/usr/bin/env sh
set -eu

usage() {
  cat >&2 <<'EOF'
usage: has_supported_btrfs_layout.sh

Passes when current system uses btrfs subvolumes mounted as:
- /     from /root
- /home from /home

Both mounts must come from same filesystem. Managed snapper configs assume
that exact layout.
EOF
}

findmnt_bin="${FINDMNT_BIN:-findmnt}"

case "${1:-}" in
  "")
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

if [ "$#" -ne 0 ]; then
  usage
  exit 2
fi

mount_field() {
  target="$1"
  field="$2"
  "$findmnt_bin" -no "$field" --target "$target" 2>/dev/null
}

normalize_subvol() {
  case "${1:-}" in
    "")
      printf '\n'
      ;;
    /*)
      printf '%s\n' "$1"
      ;;
    *)
      printf '/%s\n' "$1"
      ;;
  esac
}

extract_subvol() {
  options="${1:-}"
  old_ifs="$IFS"
  IFS=,
  set -- $options
  IFS="$old_ifs"

  for option in "$@"; do
    case "$option" in
      subvol=*)
        normalize_subvol "${option#subvol=}"
        return 0
        ;;
    esac
  done

  printf '\n'
}

root_fstype="$(mount_field / FSTYPE || true)"
root_options="$(mount_field / OPTIONS || true)"
root_majmin="$(mount_field / MAJ:MIN || true)"
home_fstype="$(mount_field /home FSTYPE || true)"
home_options="$(mount_field /home OPTIONS || true)"
home_majmin="$(mount_field /home MAJ:MIN || true)"

[ "$root_fstype" = "btrfs" ] || exit 1
[ "$home_fstype" = "btrfs" ] || exit 1
[ -n "$root_majmin" ] || exit 1
[ "$root_majmin" = "$home_majmin" ] || exit 1
[ "$(extract_subvol "$root_options")" = "/root" ] || exit 1
[ "$(extract_subvol "$home_options")" = "/home" ] || exit 1

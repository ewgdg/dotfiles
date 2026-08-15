#!/usr/bin/env sh
set -eu

usage() {
  cat >&2 <<'EOF'
usage: has_supported_btrfs_layout.sh

Passes when / and /home are separate btrfs subvolume mountpoints
on the same filesystem.

Managed snapper configs snapshot those mounted paths separately.
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

root_fstype="$(mount_field / FSTYPE || true)"
root_target="$(mount_field / TARGET || true)"
root_fsroot="$(mount_field / FSROOT || true)"
root_majmin="$(mount_field / MAJ:MIN || true)"
home_fstype="$(mount_field /home FSTYPE || true)"
home_target="$(mount_field /home TARGET || true)"
home_fsroot="$(mount_field /home FSROOT || true)"
home_majmin="$(mount_field /home MAJ:MIN || true)"

[ "$root_fstype" = "btrfs" ] || exit 1
[ "$home_fstype" = "btrfs" ] || exit 1
[ "$root_target" = "/" ] || exit 1
[ "$home_target" = "/home" ] || exit 1
[ -n "$root_majmin" ] || exit 1
[ "$root_majmin" = "$home_majmin" ] || exit 1
# FSROOT identifies each mounted subvolume without depending on its name.
[ -n "$root_fsroot" ] || exit 1
[ -n "$home_fsroot" ] || exit 1
[ "$root_fsroot" != "$home_fsroot" ] || exit 1

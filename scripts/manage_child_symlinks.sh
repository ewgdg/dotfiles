#!/bin/sh
# Mirror each visible entry of SOURCE_DIR as a symlink inside DESTINATION_DIR.
# DESTINATION_DIR stays a real directory another tool may own; only symlinks
# pointing into SOURCE_DIR are managed, so foreign entries are left untouched.
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 probe|apply DESTINATION_DIR SOURCE_DIR" >&2
  exit 2
fi

mode=$1

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_dir/home_path.sh"

expand_home_path "$2"
destination=$expanded
expand_home_path "$3"
source_dir=$expanded

if [ -L "$destination" ]; then
  # Mirroring into a symlink would create links inside SOURCE_DIR itself.
  echo "managed destination directory is a symlink: $destination" >&2
  exit 1
fi
if [ -e "$destination" ] && [ ! -d "$destination" ]; then
  echo "managed destination is not a directory: $destination" >&2
  exit 1
fi

points_into_source() {
  case $(readlink "$1") in
    "$source_dir"/*) return 0 ;;
    *) return 1 ;;
  esac
}

source_has() {
  [ -e "$source_dir/$1" ] || [ -L "$source_dir/$1" ]
}

# Reports whether any link is missing or stale; fails on unmanaged conflicts.
needs_work=false
for entry in "$source_dir"/*; do
  [ -e "$entry" ] || [ -L "$entry" ] || continue
  link=$destination/${entry##*/}
  if [ -L "$link" ]; then
    [ "$(readlink "$link")" = "$entry" ] && continue
    points_into_source "$link" || {
      echo "managed link destination points elsewhere: $link" >&2
      exit 1
    }
  elif [ -e "$link" ]; then
    echo "managed link destination is not a symlink: $link" >&2
    exit 1
  fi
  needs_work=true
done
for link in "$destination"/*; do
  [ -L "$link" ] && points_into_source "$link" && ! source_has "${link##*/}" && needs_work=true
done

case $mode in
  probe)
    if [ "$needs_work" = true ]; then exit 0; else exit 100; fi
    ;;
  apply)
    [ "$needs_work" = true ] || exit 0
    mkdir -p "$destination"
    for entry in "$source_dir"/*; do
      [ -e "$entry" ] || [ -L "$entry" ] || continue
      link=$destination/${entry##*/}
      [ -L "$link" ] && [ "$(readlink "$link")" = "$entry" ] && continue
      [ -L "$link" ] && unlink "$link"
      ln -s "$entry" "$link"
    done
    for link in "$destination"/*; do
      if [ -L "$link" ] && points_into_source "$link" && ! source_has "${link##*/}"; then
        unlink "$link"
      fi
    done
    ;;
  *)
    echo "unknown mode: $mode" >&2
    exit 2
    ;;
esac

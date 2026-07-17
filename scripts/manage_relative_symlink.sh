#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 probe|apply DESTINATION TARGET" >&2
  exit 2
fi

mode=$1
destination_spec=$2
target_spec=$3

expand_home_path() {
  path_spec=$1

  case $path_spec in
    "")
      echo "managed symlink path must not be empty" >&2
      exit 2
      ;;
    "~")
      expanded=$HOME
      ;;
    "~/"*)
      expanded=$HOME/${path_spec#??}
      ;;
    '$HOME')
      expanded=$HOME
      ;;
    '$HOME/'*)
      expanded=$HOME/${path_spec#\$HOME/}
      ;;
    '${HOME}')
      expanded=$HOME
      ;;
    '${HOME}/'*)
      expanded=$HOME/${path_spec#\$\{HOME\}/}
      ;;
    /*)
      expanded=$path_spec
      ;;
    *)
      echo "managed symlink path must be absolute or HOME-based: $path_spec" >&2
      exit 2
      ;;
  esac
}

expand_home_path "$destination_spec"
destination=$expanded
expand_home_path "$target_spec"
expected=$expanded

is_current() {
  [ -L "$destination" ] || return 1

  # The sentinel preserves payload newlines that command substitution would trim.
  readlink_output=$(readlink "$destination" && printf x) || return 2
  readlink_output=${readlink_output%x}
  newline='
'
  actual=${readlink_output%"$newline"}
  [ "$actual" = "$expected" ]
}

can_inspect_missing_destination() {
  ancestor=$(dirname "$destination")

  while [ ! -e "$ancestor" ] && [ ! -L "$ancestor" ]; do
    parent=$(dirname "$ancestor")
    [ "$parent" != "$ancestor" ] || return 1
    ancestor=$parent
  done

  [ -d "$ancestor" ] && [ -x "$ancestor" ]
}

case $mode in
  probe)
    if is_current; then
      exit 100
    else
      status=$?
      [ "$status" -eq 1 ] || exit "$status"
    fi

    [ -L "$destination" ] && exit 0
    if [ -d "$destination" ]; then
      echo "managed symlink destination is a directory: $destination" >&2
      exit 1
    fi
    [ -f "$destination" ] && exit 0
    if [ -e "$destination" ]; then
      echo "managed symlink destination has unsupported type: $destination" >&2
      exit 1
    fi
    if can_inspect_missing_destination; then
      exit 0
    fi

    echo "cannot reliably inspect managed symlink destination: $destination" >&2
    exit 1
    ;;
  apply)
    if is_current; then
      exit 0
    else
      status=$?
      [ "$status" -eq 1 ] || exit "$status"
    fi

    parent=$(dirname "$destination")
    mkdir -p "$parent"

    if [ -L "$destination" ]; then
      unlink "$destination"
    elif [ -d "$destination" ]; then
      echo "refusing to replace directory: $destination" >&2
      exit 1
    elif [ -e "$destination" ]; then
      unlink "$destination"
    fi

    ln -s "$expected" "$destination"
    ;;
  *)
    echo "unknown mode: $mode" >&2
    exit 2
    ;;
esac

# Shared by symlink helpers; sourced, not executed.

# Sets $expanded to an absolute path from ~, $HOME, ${HOME}, or absolute specs.
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

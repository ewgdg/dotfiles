# Shared by AppImage helpers; sourced, not executed. Callers define usage().

appimage_dir=$HOME/Applications
applications_dir=${XDG_DATA_HOME:-$HOME/.local/share}/applications
icons_dir=${XDG_DATA_HOME:-$HOME/.local/share}/icons
command_dir=$HOME/.local/bin
# Per-AppImage list of installed desktop entry (first line) and icons, so
# probes and re-integration never scan the shared applications/icons dirs.
record_dir=${XDG_STATE_HOME:-$HOME/.local/state}/appimages

# Sets $name, $url, $link_command, and $drop_mime_types from --name, --url,
# --link-command, --drop-mime-types.
parse_appimage_args() {
  name=""
  url=""
  link_command=false
  drop_mime_types=false
  while [ "$#" -gt 0 ]; do
    case $1 in
      --name)
        [ "$#" -ge 2 ] || usage
        name=$2
        shift 2
        ;;
      --url)
        [ "$#" -ge 2 ] || usage
        url=$2
        shift 2
        ;;
      --link-command)
        link_command=true
        shift
        ;;
      --drop-mime-types)
        drop_mime_types=true
        shift
        ;;
      *)
        usage
        ;;
    esac
  done
}

# Sets $appimage_path, $command_path, and $record_path for $name.
set_appimage_paths() {
  case $name in
    "" | *[!a-z0-9._-]*)
      printf 'invalid AppImage name (use a-z 0-9 . _ -): %s\n' "$name" >&2
      exit 64
      ;;
  esac
  appimage_path=$appimage_dir/$name.AppImage
  command_path=$command_dir/$name
  record_path=$record_dir/$name.files
}

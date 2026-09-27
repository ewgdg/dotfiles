# Shared by AppImage helpers; sourced, not executed.

appimage_dir=$HOME/Applications
applications_dir=${XDG_DATA_HOME:-$HOME/.local/share}/applications
icons_dir=${XDG_DATA_HOME:-$HOME/.local/share}/icons
command_dir=$HOME/.local/bin

# Sets $appimage_path and $command_path for AppImage <name>.
set_appimage_paths() {
  case $1 in
    "" | *[!a-z0-9._-]*)
      printf 'invalid AppImage name (use a-z 0-9 . _ -): %s\n' "$1" >&2
      exit 64
      ;;
  esac
  appimage_path=$appimage_dir/$1.AppImage
  command_path=$command_dir/$1
}

# Prints the installed desktop entry that launches $appimage_path. The entry
# keeps the AppImage's own file name so window-to-launcher matching still works.
find_desktop_entry() {
  grep -slF "Exec=\"$appimage_path\"" "$applications_dir"/*.desktop
}

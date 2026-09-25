#!/bin/sh
# Guard dotman push on a working macOS developer toolchain.
#
# Homebrew and native builds resolve compilers through the toolchain chosen by
# xcode-select. When that points at an Xcode.app that cannot run (newer than the
# OS, or license not accepted), macOS only shows an "install the command line
# developer tools" popup that installing cannot fix. Fail before planning with
# the real fix instead. `xcrun` reports the failure without the popup.
set -eu

[ "$(uname -s)" = Darwin ] || exit 0

if xcrun clang --version >/dev/null 2>&1; then
  exit 0
fi

printf '%s\n' "selected developer toolchain cannot run clang: $(xcode-select -p 2>/dev/null || echo none)" >&2
printf '%s\n' 'Select the Command Line Tools, then retry:' >&2
printf '%s\n' '  sudo xcode-select -s /Library/Developer/CommandLineTools' >&2
printf '%s\n' 'If they are not installed, run `xcode-select --install` first.' >&2
exit 1

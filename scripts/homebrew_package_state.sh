#!/bin/sh

# Succeeds when the package is installed as a formula or cask. `brew list
# --versions <name>` exits 1 silently for a package that is not installed, but
# prints an error when brew itself is broken (for example an unaccepted Xcode
# license); surface that instead of reporting the package as missing.
homebrew_package_is_installed() {
    package_name=$1

    # Homebrew's unqualified list check does not include installed casks.
    for package_kind in --formula --cask; do
        if brew_error=$(brew list "$package_kind" --versions "$package_name" 2>&1 >/dev/null); then
            return 0
        fi
        if [ -n "$brew_error" ]; then
            printf '%s\n' "$brew_error" >&2
            exit 1
        fi
    done
    return 1
}

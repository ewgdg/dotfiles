#!/bin/sh

homebrew_package_is_installed() {
    package_name=$1

    # Homebrew's unqualified list check does not include installed casks.
    brew list --formula --versions "$package_name" >/dev/null 2>&1 \
        || brew list --cask --versions "$package_name" >/dev/null 2>&1
}

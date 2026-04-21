#!/bin/sh

set -eu

package_tap_map='
bun oven-sh/bun
'

lookup_required_tap() {
    requested_package_name=$1

    while read -r mapped_package_name tap_name; do
        [ -n "$mapped_package_name" ] || continue

        if [ "$mapped_package_name" = "$requested_package_name" ]; then
            printf '%s\n' "$tap_name"
            return 0
        fi
    done <<EOF
$package_tap_map
EOF

    return 1
}

log_warning() {
    printf '%s\n' "$*" >&2
}

ensure_tap() {
    tap_name=$1

    if ! brew tap-info --installed "$tap_name" >/dev/null 2>&1; then
        if ! brew tap "$tap_name" >/dev/null 2>&1; then
            log_warning "warning: failed to tap $tap_name"
            return 1
        fi
    fi
}

package_is_installed() {
    package_name=$1

    brew list --versions "$package_name" >/dev/null 2>&1
}

brew_install_package() {
    package_name=$1

    brew install --quiet "$package_name"
}

install_package() {
    package_name=$1

    if required_tap=$(lookup_required_tap "$package_name"); then
        if ! ensure_tap "$required_tap"; then
            log_warning "warning: skipping $package_name because required tap $required_tap is unavailable"
            return 0
        fi
    fi

    brew_install_package "$package_name"
}

for package_name do
    if package_is_installed "$package_name"; then
        continue
    fi

    install_package "$package_name"
done

#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <user|system> <unit-name>" >&2
  exit 2
fi

scope="$1"
unit_name="$2"

sudo_command=(sudo)

systemctl_query_command=()
systemctl_enable_command=()
reload_before_precheck=false
manager_unreachable_message=""
unit_unavailable_message=""

case "${scope}" in
  user)
    if [[ ${EUID} -eq 0 ]]; then
      echo "Skipping ${unit_name}: user services are not enabled from a root context." >&2
      exit 0
    fi
    systemctl_query_command=(systemctl --user)
    systemctl_enable_command=(systemctl --user enable "${unit_name}")
    reload_before_precheck=true
    manager_unreachable_message="Skipping ${unit_name}: user systemd is not reachable."
    unit_unavailable_message="Skipping ${unit_name}: the unit is not available to the user manager yet."
    ;;
  system)
    systemctl_query_command=(systemctl)
    manager_unreachable_message="Skipping ${unit_name}: systemd is not reachable."
    unit_unavailable_message="Skipping ${unit_name}: the system unit is not available."
    if [[ ${EUID} -eq 0 ]]; then
      systemctl_enable_command=(systemctl enable "${unit_name}")
    else
      systemctl_enable_command=("${sudo_command[@]}" systemctl enable "${unit_name}")
    fi
    ;;
  *)
    echo "invalid scope '${scope}', expected 'user' or 'system'" >&2
    exit 2
    ;;
esac

if [[ "${reload_before_precheck}" == "true" ]] && ! "${systemctl_query_command[@]}" daemon-reload >/dev/null 2>&1; then
  echo "${manager_unreachable_message}" >&2
  exit 0
fi

if "${systemctl_query_command[@]}" --quiet is-enabled "${unit_name}" >/dev/null 2>&1; then
  echo "${unit_name} is already enabled."
  exit 0
fi

if ! "${systemctl_query_command[@]}" show --property=FragmentPath --value "${unit_name}" | grep -q .; then
  echo "${unit_unavailable_message}" >&2
  exit 0
fi

if [[ "${reload_before_precheck}" != "true" ]]; then
  if [[ ${EUID} -eq 0 ]]; then
    if ! systemctl daemon-reload >/dev/null 2>&1; then
      echo "${manager_unreachable_message}" >&2
      exit 0
    fi
  else
    if ! "${sudo_command[@]}" systemctl daemon-reload >/dev/null 2>&1; then
      echo "${manager_unreachable_message}" >&2
      exit 0
    fi
  fi
fi

"${systemctl_enable_command[@]}"

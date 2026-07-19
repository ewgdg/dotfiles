#!/usr/bin/env bash
set -euo pipefail

draft_file="${1:?draft file path is required}"
title="${GH_ISSUE_TITLE:-}"
body_file="${GH_ISSUE_BODY_FILE:-}"
inline_body="${GH_ISSUE_BODY:-}"

if [[ -z "${title}" ]]; then
  echo "GH_ISSUE_TITLE is required" >&2
  exit 2
fi

scissors_marker='------------------------ >8 ------------------------'
scissors_block=''

if grep -Fq -- "${scissors_marker}" "${draft_file}"; then
  scissors_block="$(sed -n "/^${scissors_marker}$/,\$p" "${draft_file}")"
fi

if [[ -n "${body_file}" ]]; then
  if [[ ! -f "${body_file}" ]]; then
    echo "GH_ISSUE_BODY_FILE does not exist: ${body_file}" >&2
    exit 2
  fi
  body_content="$(cat "${body_file}")"
elif [[ -n "${inline_body}" ]]; then
  body_content="${inline_body}"
else
  if [[ -n "${scissors_block}" ]]; then
    body_content="$(sed -n "2,/^${scissors_marker}$/p" "${draft_file}" | sed '$d')"
  else
    body_content="$(tail -n +2 "${draft_file}")"
  fi
fi

{
  printf '%s\n' "${title}"
  if [[ -n "${body_content}" ]]; then
    printf '%s\n' "${body_content}"
  fi
  if [[ -n "${scissors_block}" ]]; then
    printf '\n%s\n' "${scissors_block}"
  fi
} > "${draft_file}"

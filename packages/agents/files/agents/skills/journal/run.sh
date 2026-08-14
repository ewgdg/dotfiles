#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  run.sh print-path
  run.sh create --highlight <Highlight> [--importance 1-3] --author <author>

Actions:
  print-path  Print the journal filesystem directory.
  create      Create an Obsidian journal entry with QuickAdd, reading Journal body from stdin.

Optional env:
  OBSIDIAN_JOURNAL_VAULT      Vault name (default: knowledgebase)
  JOURNAL_VAULT_RELATIVE_DIR  Journal dir inside vault (default: Streams/Journals)
  JOURNAL_IMPORTANCE          Default importance if --importance omitted (default: 1)
  JOURNAL_QUICKADD_CHOICE     QuickAdd choice used for agent entries (default: Agent Journal)
  JOURNAL_CREATE_PATH_RETRIES Attempts to wait for the created note to appear (default: 10)
  JOURNAL_CREATE_PATH_SLEEP   Delay between path lookup attempts (default: 0.5)
USAGE
}

vault="${OBSIDIAN_JOURNAL_VAULT:-knowledgebase}"
journal_vault_relative_dir="${JOURNAL_VAULT_RELATIVE_DIR:-Streams/Journals}"
quickadd_choice="${JOURNAL_QUICKADD_CHOICE:-Agent Journal}"

strip_obsidian_eval_prefix() {
  sed -E 's/^=>[[:space:]]*//' | tr -d '\r' | sed -E 's/^"(.*)"$/\1/'
}

discover_vault_path() {
  local discovered=""
  local code="const adapter = app.vault.adapter; const basePath = adapter.getBasePath?.() ?? adapter.basePath ?? ''; basePath;"
  # Keep caller stdin for journal body; obsidian CLI may otherwise consume piped stdin before create_journal can read it.
  if discovered="$(obsidian vault="$vault" eval code="$code" </dev/null 2>/dev/null | strip_obsidian_eval_prefix | tail -n 1)"; then
    if [[ -n "$discovered" && "$discovered" != "undefined" && "$discovered" != "null" ]]; then
      printf '%s\n' "$discovered"
      return
    fi
  fi

  printf '%s\n' "$HOME/projects/knowledgebase"
}

resolve_journal_dir() {
  local vault_path="$1"

  python3 - "$vault_path" "$journal_vault_relative_dir" <<'PY'
from pathlib import Path
import sys

vault_path = Path(sys.argv[1]).expanduser()
journal_vault_relative_dir = Path(sys.argv[2])
print((vault_path / journal_vault_relative_dir).resolve())
PY
}

quote_yaml_string_scalar() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1], ensure_ascii=False))' "$1"
}

snapshot_journal_paths() {
  local journal_dir="$1"
  [[ -d "$journal_dir" ]] || return 0
  find "$journal_dir" -maxdepth 1 -type f -name '*.md' ! -name 'Journals.md' -print0
}

wait_for_created_journal_path() {
  local journal_dir="$1"
  local -n known_paths="$2"
  local retries="${JOURNAL_CREATE_PATH_RETRIES:-10}"
  local sleep_seconds="${JOURNAL_CREATE_PATH_SLEEP:-0.5}"
  local path=""
  local -a created_paths=()

  for ((attempt = 1; attempt <= retries; attempt++)); do
    created_paths=()
    while IFS= read -r -d '' path; do
      if [[ -z "${known_paths[$path]+present}" ]]; then
        created_paths+=("$path")
      fi
    done < <(snapshot_journal_paths "$journal_dir")

    if [[ ${#created_paths[@]} -eq 1 ]]; then
      printf '%s\n' "${created_paths[0]}"
      return 0
    fi
    if [[ ${#created_paths[@]} -gt 1 ]]; then
      printf 'Multiple journal files appeared during creation; refusing to guess which one belongs to this run.\n' >&2
      return 1
    fi
    sleep "$sleep_seconds"
  done

  return 1
}

format_created_filename() {
  local vault_path="$1"
  local journal_dir="$2"
  local created_vault_path="$3"

  python3 - "$vault_path" "$journal_dir" "$created_vault_path" <<'PY'
from pathlib import Path
import sys

vault_path = Path(sys.argv[1]).expanduser().resolve()
journal_dir = Path(sys.argv[2]).expanduser().resolve()
created_vault_path = Path(sys.argv[3])
created_path = (created_vault_path if created_vault_path.is_absolute() else vault_path / created_vault_path).resolve()

try:
    relative_path = created_path.relative_to(journal_dir)
except ValueError:
    print(f"Created journal path is not under journal dir: {created_path} not under {journal_dir}", file=sys.stderr)
    raise SystemExit(1)

if len(relative_path.parts) != 1:
    print(f"Created journal path is not directly inside journal dir: {relative_path}", file=sys.stderr)
    raise SystemExit(1)

print(str(created_path))
PY
}

validate_importance() {
  local value="$1"
  python3 - "$value" <<'PY'
import sys

raw = sys.argv[1]
try:
    value = float(raw)
except ValueError:
    print(f"Importance must be a number from 1 to 3. Got: {raw}", file=sys.stderr)
    raise SystemExit(2)

if not (1 <= value <= 3):
    print(f"Importance must be a number from 1 to 3. Got: {raw}", file=sys.stderr)
    raise SystemExit(2)
PY
}

create_journal() {
  local vault_path="$1"
  shift

  local highlight=""
  local importance="${JOURNAL_IMPORTANCE:-1}"
  local author=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --highlight)
        if [[ $# -lt 2 || -z "$2" ]]; then
          usage
          exit 2
        fi
        highlight="$2"
        shift 2
        ;;
      --importance)
        if [[ $# -lt 2 || -z "$2" ]]; then
          usage
          exit 2
        fi
        importance="$2"
        shift 2
        ;;
      --author)
        if [[ $# -lt 2 || -z "$2" ]]; then
          usage
          exit 2
        fi
        author="$2"
        shift 2
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        usage
        exit 2
        ;;
    esac
  done

  if [[ -z "$highlight" ]]; then
    usage
    exit 2
  fi
  if [[ -z "$author" ]]; then
    printf '%s\n' '--author is required; the agent must identify itself.' >&2
    usage
    exit 2
  fi
  validate_importance "$importance"

  local journal="$(cat)"
  if [[ -z "$(printf '%s' "$journal" | tr -d '[:space:]')" ]]; then
    printf 'Journal body must be provided on stdin.\n' >&2
    exit 2
  fi

  local journal_dir="$(resolve_journal_dir "$vault_path")"
  local -A existing_journal_paths=()
  local existing_path=""
  while IFS= read -r -d '' existing_path; do
    existing_journal_paths["$existing_path"]=1
  done < <(snapshot_journal_paths "$journal_dir")
  local quickadd_output=""
  # Agent Journal writes these values into YAML; quote string scalars before QuickAdd substitutes them.
  local highlight_yaml_scalar="$(quote_yaml_string_scalar "$highlight")"
  local author_yaml_scalar="$(quote_yaml_string_scalar "$author")"

  if ! quickadd_output="$(obsidian vault="$vault" quickadd:run \
    choice="$quickadd_choice" \
    value-Highlight="$highlight_yaml_scalar" \
    value-Importance="$importance" \
    value-Author="$author_yaml_scalar" \
    value-Journal="$journal" 2>&1)"; then
    printf '%s\n' "$quickadd_output" >&2
    exit 1
  fi

  local after_path=""
  if ! after_path="$(wait_for_created_journal_path "$journal_dir" existing_journal_paths)"; then
    printf '%s\n' "$quickadd_output" >&2
    printf 'Could not identify newly created journal path.\n' >&2
    exit 1
  fi

  format_created_filename "$vault_path" "$journal_dir" "$after_path"
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command="$1"
shift

case "$command" in
  print-path)
    if [[ $# -ne 0 ]]; then
      usage
      exit 2
    fi
    resolve_journal_dir "$(discover_vault_path)"
    ;;
  create)
    create_journal "$(discover_vault_path)" "$@"
    ;;
  --help|-h)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac

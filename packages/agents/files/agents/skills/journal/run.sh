#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  run.sh print-path
  run.sh create --highlight <Highlight> [--importance 1-3] [--author <author>]

Actions:
  print-path  Print the journal filesystem directory.
  create      Create an Obsidian journal entry with QuickAdd, reading Journal body from stdin.

Optional env:
  OBSIDIAN_JOURNAL_VAULT      Vault name (default: knowledgebase)
  JOURNAL_VAULT_RELATIVE_DIR  Journal dir inside vault (default: Streams/Journals)
  JOURNAL_IMPORTANCE          Default importance if --importance omitted (default: 1)
  JOURNAL_AUTHOR              Author override if --author omitted
  JOURNAL_CREATE_PATH_RETRIES Attempts to wait for Obsidian to index created note (default: 10)
  JOURNAL_CREATE_PATH_SLEEP   Delay between path lookup attempts (default: 0.5)
USAGE
}

vault="${OBSIDIAN_JOURNAL_VAULT:-knowledgebase}"
journal_vault_relative_dir="${JOURNAL_VAULT_RELATIVE_DIR:-Streams/Journals}"

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

normalize_slug_part() {
  local value="$1"
  value="${value,,}"
  value="$(printf '%s' "$value" | sed -E 's/[^a-z0-9._+-]+/-/g; s/^-+//; s/-+$//')"
  printf '%s' "$value"
}

quote_yaml_string_scalar() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1], ensure_ascii=False))' "$1"
}

detect_author() {
  local explicit_author="$1"

  if [[ -n "$explicit_author" ]]; then
    printf '%s' "$explicit_author"
    return
  fi

  local harness="${AGENT_HARNESS:-${PI_HARNESS:-${HARNESS:-}}}"
  if [[ -z "$harness" && "${PI_CODING_AGENT:-}" == "true" ]]; then
    harness="pi"
  fi
  if [[ -z "$harness" && -n "${CODEX_SANDBOX:-}" ]]; then
    harness="codex"
  fi

  local provider="${AGENT_PROVIDER:-${PI_PROVIDER:-${LLM_PROVIDER:-${PROVIDER_NAME:-${PROVIDER:-}}}}}"
  local model="${AGENT_MODEL:-${PI_MODEL:-${OPENAI_MODEL:-${ANTHROPIC_MODEL:-${LLM_MODEL:-${MODEL_NAME:-${MODEL:-}}}}}}}"

  harness="$(normalize_slug_part "$harness")"
  provider="$(normalize_slug_part "$provider")"
  model="$(normalize_slug_part "$model")"

  if [[ -n "$harness" && -n "$provider" && -n "$model" ]]; then
    printf 'agent-%s-%s-%s' "$harness" "$provider" "$model"
  elif [[ -n "$harness" && -n "$model" ]]; then
    printf 'agent-%s-%s' "$harness" "$model"
  elif [[ -n "$harness" ]]; then
    printf 'agent-%s' "$harness"
  else
    printf 'agent'
  fi
}

latest_journal_path() {
  obsidian vault="$vault" eval code="const journalDir = '$journal_vault_relative_dir'.replace(/\\/+$/, ''); const prefix = journalDir + '/'; const f = app.vault.getMarkdownFiles().filter(f => f.path.startsWith(prefix) && f.name !== 'Journals.md').sort((a, b) => b.stat.ctime - a.stat.ctime)[0]; f ? f.path : '';" \
    </dev/null | strip_obsidian_eval_prefix
}

wait_for_new_journal_path() {
  local before_path="$1"
  local retries="${JOURNAL_CREATE_PATH_RETRIES:-10}"
  local sleep_seconds="${JOURNAL_CREATE_PATH_SLEEP:-0.5}"
  local after_path=""

  for ((attempt = 1; attempt <= retries; attempt++)); do
    after_path="$(latest_journal_path)"
    if [[ -n "$after_path" && "$after_path" != "$before_path" ]]; then
      printf '%s\n' "$after_path"
      return 0
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
  local explicit_author="${JOURNAL_AUTHOR:-}"

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
        explicit_author="$2"
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
  validate_importance "$importance"

  local journal="$(cat)"
  if [[ -z "$(printf '%s' "$journal" | tr -d '[:space:]')" ]]; then
    printf 'Journal body must be provided on stdin.\n' >&2
    exit 2
  fi

  local author="$(detect_author "$explicit_author")"
  local journal_dir="$(resolve_journal_dir "$vault_path")"
  local before_path="$(latest_journal_path)"
  local quickadd_output=""
  # Journal template writes Highlight into YAML aliases; quote before QuickAdd so ':' cannot corrupt frontmatter.
  local highlight_yaml_scalar="$(quote_yaml_string_scalar "$highlight")"

  if ! quickadd_output="$(obsidian vault="$vault" quickadd:run \
    choice="Journal" \
    value-Highlight="$highlight_yaml_scalar" \
    value-Importance="$importance" \
    value-Journal="$journal" 2>&1)"; then
    printf '%s\n' "$quickadd_output" >&2
    exit 1
  fi

  local after_path=""
  if ! after_path="$(wait_for_new_journal_path "$before_path")"; then
    printf '%s\n' "$quickadd_output" >&2
    printf 'Could not identify newly created journal path; author not set.\n' >&2
    exit 1
  fi

  obsidian vault="$vault" property:set \
    path="$after_path" \
    name="author" \
    value="$author" \
    type=text >/dev/null

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

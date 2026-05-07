#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  run.sh print-path
  run.sh create --highlight <Highlight> [--author <author>]

Actions:
  print-path  Print the journal filesystem directory.
  create      Create an Obsidian journal entry with QuickAdd, reading Journal body from stdin.

Optional env:
  OBSIDIAN_JOURNAL_VAULT      Vault name (default: knowledgebase)
  JOURNAL_VAULT_RELATIVE_DIR  Journal dir inside vault (default: Streams/Journals)
  JOURNAL_AUTHOR              Author override if --author omitted
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

print(relative_path.name)
PY
}

create_journal() {
  local vault_path="$1"
  shift

  local highlight=""
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

  local journal="$(cat)"
  if [[ -z "$(printf '%s' "$journal" | tr -d '[:space:]')" ]]; then
    printf 'Journal body must be provided on stdin.\n' >&2
    exit 2
  fi

  local author="$(detect_author "$explicit_author")"
  local journal_dir="$(resolve_journal_dir "$vault_path")"
  local before_path="$(latest_journal_path)"
  local quickadd_output=""

  if ! quickadd_output="$(obsidian vault="$vault" quickadd:run \
    choice="Journal" \
    value-Highlight="$highlight" \
    value-Journal="$journal" 2>&1)"; then
    printf '%s\n' "$quickadd_output" >&2
    exit 1
  fi

  local after_path="$(latest_journal_path)"

  if [[ -z "$after_path" || "$after_path" == "$before_path" ]]; then
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

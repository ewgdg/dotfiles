#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: run.sh <Highlight> <Journal> [author]

Creates an Obsidian journal entry with QuickAdd, then sets frontmatter author.
Optional env:
  OBSIDIAN_JOURNAL_VAULT  Vault name (default: knowledgebase)
  JOURNAL_AUTHOR          Author override if third arg omitted
USAGE
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
  exit 2
fi

vault="${OBSIDIAN_JOURNAL_VAULT:-knowledgebase}"
highlight="$1"
journal="$2"
explicit_author="${3:-${JOURNAL_AUTHOR:-}}"

normalize_slug_part() {
  local value="$1"
  value="${value,,}"
  value="$(printf '%s' "$value" | sed -E 's/[^a-z0-9._+-]+/-/g; s/^-+//; s/-+$//')"
  printf '%s' "$value"
}

detect_author() {
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
  obsidian vault="$vault" eval code="const f = app.vault.getMarkdownFiles().filter(f => f.path.startsWith('Streams/Journals/') && f.name !== 'Journals.md').sort((a, b) => b.stat.ctime - a.stat.ctime)[0]; f ? f.path : '';" \
    | sed -E 's/^=>[[:space:]]*//' \
    | tr -d '\r'
}

author="$(detect_author)"
before_path="$(latest_journal_path)"
quickadd_output="$(mktemp -t obsidian-journal-quickadd.XXXXXX)"

if ! obsidian vault="$vault" quickadd:run \
  choice="Journal" \
  value-Highlight="$highlight" \
  value-Journal="$journal" >"$quickadd_output" 2>&1; then
  cat "$quickadd_output" >&2
  trash-put "$quickadd_output" 2>/dev/null || true
  exit 1
fi

after_path="$(latest_journal_path)"

if [[ -z "$after_path" || "$after_path" == "$before_path" ]]; then
  cat "$quickadd_output" >&2
  printf 'Could not identify newly created journal path; author not set.\n' >&2
  trash-put "$quickadd_output" 2>/dev/null || true
  exit 1
fi

obsidian vault="$vault" property:set \
  path="$after_path" \
  name="author" \
  value="$author" \
  type=text >/dev/null

trash-put "$quickadd_output" 2>/dev/null || true
printf '%s\n' "$after_path"

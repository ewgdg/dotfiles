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
  JOURNAL_CREATE_WAIT_SECONDS Max seconds to wait for the created note to appear (default: 5)

Exit status 3 from create means the journal was not created (e.g. name collision); retrying is safe.
USAGE
}

vault="${OBSIDIAN_JOURNAL_VAULT:-knowledgebase}"
journal_vault_relative_dir="${JOURNAL_VAULT_RELATIVE_DIR:-Streams/Journals}"
quickadd_choice="${JOURNAL_QUICKADD_CHOICE:-Agent Journal}"

discover_vault_path() {
  # Read Obsidian's vault registry directly: `obsidian` CLI stdout is intermittently empty
  # (the per-call Electron client can exit before flushing), so it cannot be relied on.
  python3 - "$vault" <<'PY'
import json
import os
import sys
from pathlib import Path

vault_name = sys.argv[1]
home = Path.home()
registry_candidates = [
    Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "obsidian/obsidian.json",
    home / "Library/Application Support/obsidian/obsidian.json",
    Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "obsidian/obsidian.json",
]
registry = next((path for path in registry_candidates if path.is_file()), None)
if registry is None:
    sys.exit("Obsidian vault registry (obsidian.json) not found.")

vault_paths = [
    entry["path"]
    for entry in json.loads(registry.read_text(encoding="utf-8"))["vaults"].values()
    if Path(entry["path"]).name == vault_name
]
if len(vault_paths) != 1:
    sys.exit(f"Expected one Obsidian vault named {vault_name!r} in {registry}, found {len(vault_paths)}.")
print(vault_paths[0])
PY
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

wait_for_own_journal() {
  # The path alone is not proof: when two callers request the same name, Obsidian keeps the first and
  # aborts the other, so each caller must see its own body in the file (frontmatter may be reformatted).
  python3 - "$1" "$2" "${JOURNAL_CREATE_WAIT_SECONDS:-5}" <<'PY'
import sys
import time
from pathlib import Path

journal_path, journal_body, wait_seconds = sys.argv[1:]
deadline = time.monotonic() + float(wait_seconds)
while time.monotonic() < deadline:
    try:
        content = Path(journal_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    if journal_body.strip() in content:
        sys.exit(0)
    time.sleep(0.1)
sys.exit(1)
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
  # The helper picks the note name so it knows the path without listing the folder or trusting CLI
  # output; the Journal choices' file-name script aborts when the name is already reserved.
  local journal_name="$(python3 -c 'from datetime import datetime; now = datetime.now(); print(now.strftime("%Y-%m-%d-%H%M%S") + f"{now.microsecond // 1000:03d}")')"
  local journal_path="$journal_dir/$journal_name.md"
  if [[ -e "$journal_path" ]]; then
    printf 'Journal already exists: %s\n' "$journal_path" >&2
    exit 3
  fi
  local quickadd_output=""
  # Agent Journal writes these values into YAML; quote string scalars before QuickAdd substitutes them.
  local highlight_yaml_scalar="$(quote_yaml_string_scalar "$highlight")"
  local author_yaml_scalar="$(quote_yaml_string_scalar "$author")"

  if ! quickadd_output="$(obsidian vault="$vault" quickadd:run \
    choice="$quickadd_choice" \
    value-Highlight="$highlight_yaml_scalar" \
    value-Importance="$importance" \
    value-Author="$author_yaml_scalar" \
    value-Journal="$journal" \
    value-JournalName="$journal_name" 2>&1)"; then
    printf '%s\n' "$quickadd_output" >&2
    exit 1
  fi

  if ! wait_for_own_journal "$journal_path" "$journal"; then
    # CLI output may be empty even on failure, so the file content is the success signal.
    [[ -n "$quickadd_output" ]] && printf '%s\n' "$quickadd_output" >&2
    printf 'Journal was not created: %s (safe to retry)\n' "$journal_path" >&2
    exit 3
  fi

  printf '%s\n' "$journal_path"
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command="$1"
shift
# Assigned separately: a failing `$(...)` used as a command argument would not trigger `set -e`.
vault_path=""

case "$command" in
  print-path)
    if [[ $# -ne 0 ]]; then
      usage
      exit 2
    fi
    vault_path="$(discover_vault_path)"
    resolve_journal_dir "$vault_path"
    ;;
  create)
    vault_path="$(discover_vault_path)"
    create_journal "$vault_path" "$@"
    ;;
  --help|-h)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac

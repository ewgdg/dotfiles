#!/usr/bin/env bash
set -euo pipefail

repo=""
json=0

usage() {
  cat <<'USAGE'
Usage: list_issue_templates.sh [-R owner/repo] [--json]

Lists GitHub issue templates from the current checkout or a remote GitHub repo.
Extracts common metadata keys: name, description, about, title, labels, assignees.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -R|--repo)
      repo="${2:?repo is required after $1}"
      shift 2
      ;;
    --json)
      json=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

tmp_dir=""
cleanup() {
  if [[ -n "${tmp_dir}" && -d "${tmp_dir}" ]]; then
    trash-put "${tmp_dir}" 2>/dev/null || rm -rf "${tmp_dir}"
  fi
}
trap cleanup EXIT

copy_remote_templates() {
  local target_dir="$1"

  command -v gh >/dev/null || { echo "gh is required for remote template inspection" >&2; exit 2; }
  command -v jq >/dev/null || { echo "jq is required for remote template inspection" >&2; exit 2; }
  command -v base64 >/dev/null || { echo "base64 is required for remote template inspection" >&2; exit 2; }

  local listing
  if ! listing="$(gh api "repos/${repo}/contents/.github/ISSUE_TEMPLATE" 2>/dev/null)"; then
    return 1
  fi

  jq -r '.[] | select(.type == "file") | select(.name | test("\\.(md|ya?ml)$")) | [.name, .path] | @tsv' <<<"${listing}" |
    while IFS=$'\t' read -r name path; do
      [[ -n "${name}" && "${name}" != "config.yml" && "${name}" != "config.yaml" ]] || continue
      gh api "repos/${repo}/contents/${path}" --jq .content | base64 -d > "${target_dir}/${name}"
    done
}

template_dir=""
if [[ -n "${repo}" ]]; then
  tmp_dir="$(mktemp -d)"
  template_dir="${tmp_dir}"
  if ! copy_remote_templates "${template_dir}"; then
    if [[ "${json}" -eq 1 ]]; then
      printf '[]\n'
    else
      echo "No .github/ISSUE_TEMPLATE directory found for ${repo}."
    fi
    exit 0
  fi
else
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  template_dir="${repo_root}/.github/ISSUE_TEMPLATE"
  if [[ ! -d "${template_dir}" ]]; then
    if [[ "${json}" -eq 1 ]]; then
      printf '[]\n'
    else
      echo "No local .github/ISSUE_TEMPLATE directory found."
    fi
    exit 0
  fi
fi

python3 - "${template_dir}" "${json}" <<'PY'
import json
import re
import sys
from pathlib import Path

template_dir = Path(sys.argv[1])
as_json = sys.argv[2] == "1"
interesting_keys = {"name", "description", "about", "title", "labels", "assignees"}


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {"'", '"'} and value[-1:] == value[0]:
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
        return [item for item in items if item]
    return value


def extract_metadata(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata = {}

    if path.suffix.lower() == ".md" and text.startswith("---"):
        parts = text.split("---", 2)
        header = parts[1] if len(parts) >= 3 else ""
    else:
        # Issue-form metadata lives before body:. Avoid parsing field definitions.
        header = text.split("\nbody:", 1)[0]

    pending_list_key = None
    for line in header.splitlines():
        if pending_list_key:
            list_item = re.match(r"^\s+-\s*(.*)$", line)
            if list_item:
                metadata.setdefault(pending_list_key, []).append(parse_scalar(list_item.group(1)))
                continue
            pending_list_key = None

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        if key in interesting_keys:
            parsed = parse_scalar(raw_value)
            metadata[key] = parsed
            if parsed == "":
                metadata[key] = []
                pending_list_key = key

    return metadata


templates = []
for path in sorted(template_dir.iterdir()):
    if not path.is_file() or path.name in {"config.yml", "config.yaml"}:
        continue
    if path.suffix.lower() not in {".md", ".yml", ".yaml"}:
        continue
    templates.append({"file": path.name, "metadata": extract_metadata(path)})

if as_json:
    print(json.dumps(templates, indent=2, ensure_ascii=False))
else:
    if not templates:
        print("No issue template files found.")
    for item in templates:
        print(item["file"])
        for key, value in item["metadata"].items():
            if isinstance(value, list):
                value = ", ".join(value)
            print(f"  {key}: {value}")
PY

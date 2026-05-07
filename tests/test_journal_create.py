from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_SH = REPO_ROOT / "packages/agents/files/agents/skills/journal/run.sh"


def write_fake_obsidian(bin_dir: Path, vault_root: Path) -> None:
    fake_obsidian = bin_dir / "obsidian"
    fake_obsidian.write_text(
        textwrap.dedent(
            rf'''
            #!/usr/bin/env bash
            set -euo pipefail

            vault_root={str(vault_root)!r}

            if [[ "${{1:-}}" == "vault="* ]]; then
              shift
            fi

            journal_relative_dir="${{JOURNAL_VAULT_RELATIVE_DIR:-Streams/Journals}}"

            latest_journal_path() {{
              find "$vault_root/$journal_relative_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null \
                | sort \
                | tail -n 1 \
                | sed "s#^$vault_root/##"
            }}

            case "${{1:-}}" in
              eval)
                code=""
                for arg in "$@"; do
                  case "$arg" in
                    code=*) code="${{arg#code=}}" ;;
                  esac
                done
                if [[ "$code" == *"getBasePath"* || "$code" == *"basePath"* ]]; then
                  printf '=> %s\n' "$vault_root"
                else
                  printf '=> %s\n' "$(latest_journal_path)"
                fi
                ;;
              quickadd:run)
                shift
                highlight=""
                journal=""
                for arg in "$@"; do
                  case "$arg" in
                    value-Highlight=*) highlight="${{arg#value-Highlight=}}" ;;
                    value-Journal=*) journal="${{arg#value-Journal=}}" ;;
                  esac
                done

                mkdir -p "$vault_root/$journal_relative_dir"
                count=$(find "$vault_root/$journal_relative_dir" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')
                next=$((count + 1))
                filename=$(printf '2026-01-01-00000%d.md' "$next")
                path="$journal_relative_dir/$filename"
                cat >"$vault_root/$path" <<EOF
            ---
            created: 2026-01-01T00:00:0${{next}}.000Z
            day: "[[2026-01-01]]"
            aliases: $highlight
            ---

            $journal
            EOF
                printf '%s\n' "$path"
                ;;
              property:set)
                path=""
                name=""
                value=""
                for arg in "$@"; do
                  case "$arg" in
                    path=*) path="${{arg#path=}}" ;;
                    name=*) name="${{arg#name=}}" ;;
                    value=*) value="${{arg#value=}}" ;;
                  esac
                done
                file="$vault_root/$path"
                python - "$file" "$name" "$value" <<'PY'
            from pathlib import Path
            import sys

            path = Path(sys.argv[1])
            name = sys.argv[2]
            value = sys.argv[3]
            text = path.read_text()
            lines = text.splitlines()
            if lines[:1] != ["---"]:
                raise SystemExit("missing frontmatter")
            end = lines.index("---", 1)
            frontmatter = lines[1:end]
            body = lines[end + 1 :]
            entry = f"{{name}}: {{value}}"
            for index, line in enumerate(frontmatter):
                if line.startswith(f"{{name}}:"):
                    frontmatter[index] = entry
                    break
            else:
                frontmatter.append(entry)
            path.write_text("\n".join(["---", *frontmatter, "---", *body]) + "\n")
            PY
                ;;
              *)
                printf 'unsupported fake obsidian command: %s\n' "$*" >&2
                exit 2
                ;;
            esac
            '''
        ).strip()
        + "\n"
    )
    fake_obsidian.chmod(0o755)


def run_journal(
    vault_root: Path,
    bin_dir: Path,
    *args: str,
    journal: str = "Body from stdin.",
    check: bool = True,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [str(RUN_SH), *args],
        cwd=REPO_ROOT,
        env=env,
        input=journal,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def journal_files(vault_root: Path, relative_dir: str = "Streams/Journals") -> list[Path]:
    return sorted((vault_root / relative_dir).glob("*.md"))


def test_journal_print_path_discovers_vault_path_from_obsidian(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_obsidian(bin_dir, vault_root)

    result = run_journal(vault_root, bin_dir, "print-path")

    assert result.stdout.strip() == str(vault_root / "Streams/Journals")
    assert not (vault_root / "Streams/Journals").exists()


def test_journal_print_path_respects_vault_relative_dir_override(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_obsidian(bin_dir, vault_root)

    result = run_journal(
        vault_root,
        bin_dir,
        "print-path",
        env_overrides={"JOURNAL_VAULT_RELATIVE_DIR": "Custom/Journals"},
    )

    assert result.stdout.strip() == str(vault_root / "Custom/Journals")


def test_journal_create_reads_body_from_stdin_and_sets_author(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_obsidian(bin_dir, vault_root)

    result = run_journal(
        vault_root,
        bin_dir,
        "create",
        "--highlight",
        "Journal writes became stdin-only notes",
        "--author",
        "agent-test",
        journal="Dropped positional body args; journal body now comes from stdin.\nQuotes `safe`.",
    )

    assert result.stdout.strip() == "2026-01-01-000001.md"
    files = journal_files(vault_root)
    assert len(files) == 1
    content = files[0].read_text()
    assert "aliases: Journal writes became stdin-only notes" in content
    assert "author: agent-test" in content
    assert "Dropped positional body args" in content
    assert "Quotes `safe`." in content


def test_journal_create_always_creates_new_note(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_obsidian(bin_dir, vault_root)

    first = run_journal(vault_root, bin_dir, "create", "--highlight", "First highlight", journal="First body")
    second = run_journal(vault_root, bin_dir, "create", "--highlight", "Second highlight", journal="Second body")

    assert first.stdout.strip() == "2026-01-01-000001.md"
    assert second.stdout.strip() == "2026-01-01-000002.md"
    assert len(journal_files(vault_root)) == 2


def test_journal_create_respects_vault_relative_dir_override(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_obsidian(bin_dir, vault_root)

    result = run_journal(
        vault_root,
        bin_dir,
        "create",
        "--highlight",
        "Custom journal dir",
        journal="Created under custom vault-relative dir.",
        env_overrides={"JOURNAL_VAULT_RELATIVE_DIR": "Custom/Journals"},
    )

    assert result.stdout.strip() == "2026-01-01-000001.md"
    assert len(journal_files(vault_root, "Custom/Journals")) == 1


def test_journal_create_rejects_missing_subcommand(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_obsidian(bin_dir, vault_root)

    result = run_journal(vault_root, bin_dir, "--highlight", "Body", check=False)

    assert result.returncode == 2
    assert "run.sh create --highlight <Highlight> [--author <author>]" in result.stderr
    assert not (vault_root / "Streams/Journals").exists()


def test_journal_create_requires_stdin_body(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_obsidian(bin_dir, vault_root)

    result = run_journal(vault_root, bin_dir, "create", "--highlight", "Only highlight", journal="   \n", check=False)

    assert result.returncode == 2
    assert "Journal body must be provided on stdin." in result.stderr
    assert not (vault_root / "Streams/Journals").exists()

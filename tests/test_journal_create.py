from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_SH = REPO_ROOT / "packages/agents/files/agents/skills/journal/run.sh"
VAULT_NAME = "knowledgebase"


def write_vault_registry(config_home: Path, vault_root: Path) -> None:
    registry = config_home / "obsidian/obsidian.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"vaults": {"a1": {"path": str(vault_root), "ts": 1}}}))


def write_fake_obsidian(bin_dir: Path, vault_root: Path) -> None:
    """Fake QuickAdd `Agent Journal` run: writes the note named by value-JournalName.

    FAKE_OBSIDIAN_MODE simulates the real failure modes:
    - `silent`: the note is created but CLI stdout is dropped (observed intermittently).
    - `lost-name-race`: another caller already holds the requested name; its note is there instead.
    - `no-create`: the run aborts without creating anything and without output.
    """
    fake_obsidian = bin_dir / "obsidian"
    fake_obsidian.write_text(
        textwrap.dedent(
            rf'''
            #!/usr/bin/env bash
            set -euo pipefail

            vault_root={str(vault_root)!r}
            journal_relative_dir="${{JOURNAL_VAULT_RELATIVE_DIR:-Streams/Journals}}"

            if [[ "${{1:-}}" == "vault="* ]]; then
              shift
            fi
            if [[ "${{1:-}}" != "quickadd:run" ]]; then
              printf 'unsupported fake obsidian command: %s\n' "$*" >&2
              exit 2
            fi
            shift

            choice="" highlight="" importance="" author="" journal="" journal_name=""
            for arg in "$@"; do
              case "$arg" in
                choice=*) choice="${{arg#choice=}}" ;;
                value-Highlight=*) highlight="${{arg#value-Highlight=}}" ;;
                value-Importance=*) importance="${{arg#value-Importance=}}" ;;
                value-Author=*) author="${{arg#value-Author=}}" ;;
                value-Journal=*) journal="${{arg#value-Journal=}}" ;;
                value-JournalName=*) journal_name="${{arg#value-JournalName=}}" ;;
              esac
            done
            if [[ "$choice" != "Agent Journal" || -z "$author" || -z "$journal_name" ]]; then
              printf 'bad quickadd:run args: %s\n' "$*" >&2
              exit 2
            fi

            mode="${{FAKE_OBSIDIAN_MODE:-normal}}"
            path="$journal_relative_dir/$journal_name.md"
            mkdir -p "$vault_root/$journal_relative_dir"
            case "$mode" in
              no-create) exit 0 ;;
              lost-name-race) journal="Another agent's journal body." ;;
            esac
            cat >"$vault_root/$path" <<EOF
            ---
            created: 2026-01-01T00:00:00.000Z
            day: "[[2026-01-01]]"
            aliases: $highlight
            importance: $importance
            author: $author
            ---

            $journal
            EOF
            if [[ "$mode" == "normal" ]]; then
              printf '{{"ok":true,"file":"%s"}}\n' "$path"
            fi
            '''
        ).strip()
        + "\n"
    )
    fake_obsidian.chmod(0o755)


def make_env(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    vault_root = tmp_path / VAULT_NAME
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    config_home = tmp_path / "config"
    write_fake_obsidian(bin_dir, vault_root)
    write_vault_registry(config_home, vault_root)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "XDG_CONFIG_HOME": str(config_home),
        "HOME": str(tmp_path / "home"),
        "OBSIDIAN_JOURNAL_VAULT": VAULT_NAME,
        "JOURNAL_CREATE_WAIT_SECONDS": "0.5",
    }
    return vault_root, bin_dir, env


def run_journal(
    env: dict[str, str],
    *args: str,
    journal: str = "Body from stdin.",
    check: bool = True,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUN_SH), *args],
        cwd=REPO_ROOT,
        env={**os.environ, **env, **(env_overrides or {})},
        input=journal,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=20,
    )


def create_args(highlight: str = "A highlight") -> list[str]:
    return ["create", "--highlight", highlight, "--author", "agent-test"]


def journal_files(vault_root: Path, relative_dir: str = "Streams/Journals") -> list[Path]:
    return sorted((vault_root / relative_dir).glob("*.md"))


def test_print_path_reads_vault_path_from_obsidian_registry(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(env, "print-path")

    assert result.stdout.strip() == str(vault_root / "Streams/Journals")
    assert not (vault_root / "Streams/Journals").exists()


def test_print_path_respects_vault_relative_dir_override(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(env, "print-path", env_overrides={"JOURNAL_VAULT_RELATIVE_DIR": "Custom/Journals"})

    assert result.stdout.strip() == str(vault_root / "Custom/Journals")


def test_print_path_fails_when_vault_is_not_registered(tmp_path: Path) -> None:
    _, _, env = make_env(tmp_path)

    result = run_journal(env, "print-path", check=False, env_overrides={"OBSIDIAN_JOURNAL_VAULT": "missing"})

    assert result.returncode != 0
    assert "'missing'" in result.stderr


def test_create_reads_body_from_stdin_and_sets_metadata(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(
        env,
        "create",
        "--highlight",
        "Journal writes became stdin-only notes",
        "--importance",
        "2",
        "--author",
        "agent-test",
        journal="Dropped positional body args; journal body now comes from stdin.\nQuotes `safe`.",
    )

    files = journal_files(vault_root)
    assert len(files) == 1
    assert result.stdout.strip() == str(files[0])
    content = files[0].read_text()
    assert 'aliases: "Journal writes became stdin-only notes"' in content
    assert "importance: 2" in content
    assert 'author: "agent-test"' in content
    assert "Dropped positional body args" in content
    assert "Quotes `safe`." in content


def test_create_always_creates_new_note(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    first = run_journal(env, *create_args("First"), journal="First body")
    second = run_journal(env, *create_args("Second"), journal="Second body")

    assert first.stdout.strip() != second.stdout.strip()
    assert "First body" in Path(first.stdout.strip()).read_text()
    assert "Second body" in Path(second.stdout.strip()).read_text()
    assert len(journal_files(vault_root)) == 2


def test_create_succeeds_when_obsidian_cli_output_is_dropped(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(env, *create_args(), journal="Created silently.", env_overrides={"FAKE_OBSIDIAN_MODE": "silent"})

    assert result.stdout.strip() == str(journal_files(vault_root)[0])


def test_create_exits_3_when_another_caller_holds_the_name(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(
        env, *create_args(), journal="My body.", check=False, env_overrides={"FAKE_OBSIDIAN_MODE": "lost-name-race"}
    )

    assert result.returncode == 3
    assert "safe to retry" in result.stderr
    assert "Another agent's journal body." in journal_files(vault_root)[0].read_text()


def test_create_exits_3_when_no_note_is_created(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(env, *create_args(), check=False, env_overrides={"FAKE_OBSIDIAN_MODE": "no-create"})

    assert result.returncode == 3
    assert "safe to retry" in result.stderr
    assert journal_files(vault_root) == []


def test_create_respects_vault_relative_dir_override(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(env, *create_args(), env_overrides={"JOURNAL_VAULT_RELATIVE_DIR": "Custom/Journals"})

    files = journal_files(vault_root, "Custom/Journals")
    assert len(files) == 1
    assert result.stdout.strip() == str(files[0])


def test_create_rejects_missing_subcommand(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(env, "--highlight", "Body", check=False)

    assert result.returncode == 2
    assert "run.sh create --highlight <Highlight> [--importance 1-3] --author <author>" in result.stderr
    assert not (vault_root / "Streams/Journals").exists()


def test_create_requires_stdin_body(tmp_path: Path) -> None:
    vault_root, _, env = make_env(tmp_path)

    result = run_journal(env, *create_args(), journal="   \n", check=False)

    assert result.returncode == 2
    assert "Journal body must be provided on stdin." in result.stderr
    assert not (vault_root / "Streams/Journals").exists()

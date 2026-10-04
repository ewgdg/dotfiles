from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_PY = REPO_ROOT / "packages/agents/files/agents/skills/agent-tasks/run.py"
VAULT_NAME = "knowledgebase"
TASKS_DIR = "Effects/Tasks"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    vault_root = tmp_path / VAULT_NAME
    (vault_root / TASKS_DIR).mkdir(parents=True)
    registry = tmp_path / "config/obsidian/obsidian.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"vaults": {"a1": {"path": str(vault_root), "ts": 1}}}))
    return vault_root


def run_tasks(vault: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "XDG_CONFIG_HOME": str(vault.parent / "config")}
    return subprocess.run(
        [str(RUN_PY), *args], input=stdin, capture_output=True, text=True, env=env, timeout=60
    )


def create_task(vault: Path, title: str, *blocked_by: str) -> str:
    blocker_args = [arg for blocker in blocked_by for arg in ("--blocked-by", blocker)]
    result = run_tasks(
        vault,
        "create", "--title", title, *blocker_args,
        stdin=f"## Brief\n{title}.\n\n## Done when\nIt works.\n",
    )
    assert result.returncode == 0, result.stderr
    return Path(result.stdout.strip()).stem


def ready_titles(vault: Path, *args: str) -> list[str]:
    result = run_tasks(vault, "ready", *args)
    assert result.returncode == 0, result.stderr
    return [line.split("\t")[1] for line in result.stdout.splitlines()]


def finish(vault: Path, task: str, *args: str) -> subprocess.CompletedProcess[str]:
    return run_tasks(vault, "finish", task, *args, stdin="Merged https://example.com/pr/1.\n")


def test_create_writes_agent_owned_tasknote_with_blockers(vault: Path) -> None:
    blocker = create_task(vault, "Design schema")
    task = create_task(vault, "Build API", blocker)

    note = (vault / TASKS_DIR / f"{task}.md").read_text()

    assert "type: task\n" in note
    assert "owner: agent\n" in note
    assert "status: open\n" in note
    assert 'aliases: "Build API"\n' in note
    assert "projects:" not in note
    assert f'  - uid: "[[{blocker}]]"\n    reltype: FINISHTOSTART\n' in note
    assert note.rstrip().endswith("## Result")


def test_create_rejects_unknown_blocker(vault: Path) -> None:
    unknown_blocker = run_tasks(
        vault, "create", "--title", "t", "--blocked-by", "nope", stdin="## Brief\nx\n\n## Done when\ny\n"
    )

    assert unknown_blocker.returncode != 0 and "nope" in unknown_blocker.stderr
    assert list((vault / TASKS_DIR).iterdir()) == []


def test_ready_lists_only_open_agent_tasks_whose_blockers_are_done(vault: Path) -> None:
    schema = create_task(vault, "Design schema")
    create_task(vault, "Build API", schema)
    (vault / TASKS_DIR / "human.md").write_text("---\ntype: task\nstatus: open\naliases: Mine\n---\n")

    assert ready_titles(vault) == ["Design schema"]

    assert run_tasks(vault, "claim", schema, "--thread", "thread-1").returncode == 0
    assert ready_titles(vault) == []

    assert finish(vault, schema).returncode == 0
    assert ready_titles(vault) == ["Build API"]


def test_claim_is_exclusive_and_finish_records_result(vault: Path) -> None:
    task = create_task(vault, "Design schema")

    first_claim = run_tasks(vault, "claim", task, "--thread", "thread-1")
    second_claim = run_tasks(vault, "claim", task, "--thread", "thread-2")
    finished = finish(vault, task)

    note = (vault / TASKS_DIR / f"{task}.md").read_text()
    assert first_claim.returncode == 0
    assert second_claim.returncode != 0 and "in-progress" in second_claim.stderr
    assert finished.returncode == 0
    assert "status: done\n" in note
    assert "claimedBy: thread-1\n" in note
    assert "completedDate: " in note
    assert note.rstrip().endswith("## Result\nMerged https://example.com/pr/1.")


def test_failed_task_is_paused_for_replanning_and_keeps_dependents_blocked(vault: Path) -> None:
    schema = create_task(vault, "Design schema")
    create_task(vault, "Build API", schema)
    run_tasks(vault, "claim", schema, "--thread", "thread-1")

    failed = finish(vault, schema, "--outcome", "failed")

    assert failed.returncode == 0
    assert "status: paused\n" in (vault / TASKS_DIR / f"{schema}.md").read_text()
    assert ready_titles(vault) == []


def test_status_update_preserves_untouched_frontmatter_bytes(vault: Path) -> None:
    task = create_task(vault, "Design schema")
    path = vault / TASKS_DIR / f"{task}.md"
    # Simulate TaskNotes' own formatting, which a YAML library round-trip would rewrite.
    path.write_text(path.read_text().replace("status: open\n", "status: open\nscheduled: 2026-03-14\n"))
    before = path.read_text()

    run_tasks(vault, "claim", task, "--thread", "thread-1")

    after = path.read_text()
    assert "scheduled: 2026-03-14\n" in after
    assert before.split("dateModified:")[0].replace("status: open", "status: in-progress") == after.split(
        "dateModified:"
    )[0]

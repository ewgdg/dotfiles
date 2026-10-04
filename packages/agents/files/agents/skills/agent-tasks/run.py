#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6"]
# ///
"""Manage agent-owned subtasks as TaskNotes in the Obsidian vault, by writing files directly."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

VAULT_NAME = os.environ.get("AGENT_TASKS_VAULT", "knowledgebase")
TASKS_RELATIVE_DIR = os.environ.get("AGENT_TASKS_VAULT_RELATIVE_DIR", "Effects/Tasks")
AGENT_OWNER = "agent"
CREATE_ATTEMPTS = 5
PLAIN_SCALAR = re.compile(r"^[\w.:+\-]+$")
FRONTMATTER = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
RESULT_HEADING = "## Result"
STATUS_FOR_OUTCOME = {"done": "done", "failed": "paused"}


class TaskError(Exception):
    pass


@dataclass(frozen=True)
class Task:
    path: Path
    frontmatter_text: str
    body: str

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def fields(self) -> dict:
        # BaseLoader keeps every scalar a string, so dates read exactly as TaskNotes wrote them.
        return yaml.load(self.frontmatter_text, Loader=yaml.BaseLoader) or {}

    @property
    def status(self) -> str:
        return self.fields.get("status", "")

    @property
    def is_agent_owned(self) -> bool:
        return self.fields.get("owner") == AGENT_OWNER

    @property
    def blocker_stems(self) -> list[str]:
        return [unwrap_link(blocker["uid"]) for blocker in self.fields.get("blockedBy", [])]

    @property
    def title(self) -> str:
        aliases = self.fields.get("aliases", self.stem)
        return aliases[0] if isinstance(aliases, list) else aliases


def discover_vault_path() -> Path:
    # Read Obsidian's vault registry directly instead of the `obsidian` CLI, which needs the app running.
    home = Path.home()
    registry_candidates = [
        Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "obsidian/obsidian.json",
        home / "Library/Application Support/obsidian/obsidian.json",
        Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "obsidian/obsidian.json",
    ]
    registry = next((path for path in registry_candidates if path.is_file()), None)
    if registry is None:
        raise TaskError("Obsidian vault registry (obsidian.json) not found.")
    vault_paths = [
        Path(entry["path"])
        for entry in json.loads(registry.read_text(encoding="utf-8"))["vaults"].values()
        if Path(entry["path"]).name == VAULT_NAME
    ]
    if len(vault_paths) != 1:
        raise TaskError(
            f"Expected one Obsidian vault named {VAULT_NAME!r} in {registry}, found {len(vault_paths)}. "
            "Set AGENT_TASKS_VAULT to the vault folder name."
        )
    return vault_paths[0]


def tasks_dir() -> Path:
    return discover_vault_path() / TASKS_RELATIVE_DIR


def unwrap_link(link: str) -> str:
    # TaskNotes may write path-style links such as [[Effects/Tasks/name.md|alias]]; reduce them to the note name.
    target = link.removeprefix("[[").removesuffix("]]").split("|")[0]
    return target.rsplit("/", 1)[-1].removesuffix(".md")


def task_link(stem: str) -> str:
    return f"[[{stem}]]"


def blocker_entry(stem: str) -> dict[str, str]:
    return {"uid": task_link(stem), "reltype": "FINISHTOSTART"}


def task_stem_list(value: str) -> list[str]:
    # Comma-separated like gh's relationship flags; combined with action="extend" it is also repeatable.
    return [stem.strip() for stem in value.split(",") if stem.strip()]


def yaml_scalar(value: str) -> str:
    # JSON strings are valid YAML double-quoted scalars.
    return value if PLAIN_SCALAR.match(value) else json.dumps(value, ensure_ascii=False)


def now_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def read_task(path: Path) -> Task:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if match is None:
        raise TaskError(f"No frontmatter in {path}")
    return Task(path=path, frontmatter_text=match.group(1), body=text[match.end():])


def load_task(stem: str) -> Task:
    path = tasks_dir() / f"{stem}.md"
    if not path.is_file():
        raise TaskError(f"Task not found: {stem}")
    return read_task(path)


def all_tasks() -> list[Task]:
    return [read_task(path) for path in sorted(tasks_dir().glob("*.md")) if FRONTMATTER.match(path.read_text(encoding="utf-8"))]


def is_ready(task: Task, tasks_by_stem: dict[str, Task]) -> bool:
    return (
        task.is_agent_owned
        and task.status == "open"
        and all(stem in tasks_by_stem and tasks_by_stem[stem].status == "done" for stem in task.blocker_stems)
    )


def render_frontmatter_key(key: str, value: str | list[str | dict[str, str]]) -> str:
    """Render one top-level key in TaskNotes' layout; an empty list renders as nothing, dropping the key."""
    if isinstance(value, str):
        return f"{key}: {yaml_scalar(value)}\n"
    lines = [f"{key}:"] if value else []
    for item in value:
        if isinstance(item, dict):
            (first_key, first_value), *rest = item.items()
            lines.append(f"  - {first_key}: {yaml_scalar(first_value)}")
            lines += [f"    {item_key}: {yaml_scalar(item_value)}" for item_key, item_value in rest]
        else:
            lines.append(f"  - {yaml_scalar(item)}")
    return "".join(f"{line}\n" for line in lines)


def update_frontmatter(task: Task, updates: dict[str, str | list]) -> None:
    # Rewrite only the touched keys' blocks: a YAML round-trip would reformat TaskNotes' dates and lists.
    frontmatter_text = task.frontmatter_text
    for key, value in updates.items():
        rendered = render_frontmatter_key(key, value)
        # A key's block is its own line plus the indented or "- " item lines beneath it.
        key_block = re.compile(rf"^{re.escape(key)}:.*\n(?:(?:[ \t]+|- ).*\n)*", re.MULTILINE)
        if key_block.search(frontmatter_text):
            frontmatter_text = key_block.sub(lambda _: rendered, frontmatter_text, count=1)
        else:
            frontmatter_text += rendered
    task.path.write_text(f"---\n{frontmatter_text}---\n{task.body}", encoding="utf-8")


def read_stdin(name: str) -> str:
    text = sys.stdin.read().strip()
    if not text:
        raise TaskError(f"{name} must be provided on stdin.")
    return text


def render_new_task(title: str, parent_stem: str | None, blocker_stems: list[str], brief: str) -> str:
    timestamp = now_timestamp()
    return (
        "---\n"
        "type: task\n"
        f"owner: {AGENT_OWNER}\n"
        "status: open\n"
        "priority: normal\n"
        f"dateCreated: {timestamp}\n"
        f"dateModified: {timestamp}\n"
        f"aliases: {json.dumps(title, ensure_ascii=False)}\n"
        # TaskNotes treats a task listed in `projects` as the parent of this one.
        + render_frontmatter_key("projects", [task_link(parent_stem)] if parent_stem else [])
        + render_frontmatter_key("blockedBy", [blocker_entry(stem) for stem in blocker_stems])
        + f"---\n\n{brief}\n\n{RESULT_HEADING}\n"
    )


def write_new_task_file(directory: Path, content: str) -> Path:
    # Names are second-resolution timestamps; exclusive create keeps concurrent creators from overwriting each other.
    for _ in range(CREATE_ATTEMPTS):
        path = directory / f"{datetime.now():%Y-%m-%d-%H%M%S}.md"
        try:
            with path.open("x", encoding="utf-8") as task_file:
                task_file.write(content)
            return path
        except FileExistsError:
            time.sleep(1)
    raise TaskError(f"Could not pick a free task file name in {directory}.")


def command_print_path(_: argparse.Namespace) -> None:
    print(tasks_dir())


def require_tasks_exist(directory: Path, role: str, stems: list[str]) -> None:
    for stem in stems:
        if not (directory / f"{stem}.md").is_file():
            raise TaskError(f"{role} task not found: {stem}")


def command_create(args: argparse.Namespace) -> None:
    directory = tasks_dir()
    require_tasks_exist(directory, "Parent", [args.parent] if args.parent else [])
    require_tasks_exist(directory, "Blocker", args.blocked_by)
    brief = read_stdin("Brief")
    print(write_new_task_file(directory, render_new_task(args.title, args.parent, args.blocked_by, brief)))


def command_edit(args: argparse.Namespace) -> None:
    directory = tasks_dir()
    task = load_task(args.task)
    if not task.is_agent_owned:
        raise TaskError(f"Task {task.stem} is not agent-owned; change the user's tasks in TaskNotes.")
    require_tasks_exist(directory, "Parent", [args.parent] if args.parent else [])
    require_tasks_exist(directory, "Blocker", args.add_blocked_by)
    if task.stem in [args.parent, *args.add_blocked_by]:
        raise TaskError(f"Task {task.stem} cannot be its own parent or blocker.")

    fields = task.fields
    projects = fields.get("projects", [])
    projects = [projects] if isinstance(projects, str) else projects
    updates: dict[str, str | list] = {}
    if args.parent or args.remove_parent:
        # A parent is a `projects` entry that is a task; other project links belong to the user and stay.
        non_task_projects = [link for link in projects if not (directory / f"{unwrap_link(link)}.md").is_file()]
        updates["projects"] = non_task_projects + ([task_link(args.parent)] if args.parent else [])
    if args.add_blocked_by or args.remove_blocked_by:
        kept_blockers = [entry for entry in fields.get("blockedBy", []) if unwrap_link(entry["uid"]) not in args.remove_blocked_by]
        kept_stems = {unwrap_link(entry["uid"]) for entry in kept_blockers}
        updates["blockedBy"] = kept_blockers + [blocker_entry(stem) for stem in dict.fromkeys(args.add_blocked_by) if stem not in kept_stems]
    if not updates:
        raise TaskError("Nothing to edit; pass a relationship flag.")
    update_frontmatter(task, {**updates, "dateModified": now_timestamp()})


def command_ready(args: argparse.Namespace) -> None:
    tasks_by_stem = {task.stem: task for task in all_tasks()}
    for task in tasks_by_stem.values():
        if is_ready(task, tasks_by_stem):
            print(f"{task.stem}\t{task.title}")


def command_claim(args: argparse.Namespace) -> None:
    task = load_task(args.task)
    if task.status != "open":
        raise TaskError(f"Task {task.stem} is {task.status}, not open.")
    if not is_ready(task, {other.stem: other for other in all_tasks()}):
        raise TaskError(f"Task {task.stem} is not ready: blockers unfinished or not agent-owned.")
    update_frontmatter(task, {"status": "in-progress", "claimedBy": args.thread, "dateModified": now_timestamp()})


def command_finish(args: argparse.Namespace) -> None:
    task = load_task(args.task)
    if task.status != "in-progress":
        raise TaskError(f"Task {task.stem} is {task.status}, not in-progress.")
    if RESULT_HEADING not in task.body:
        raise TaskError(f"Task {task.stem} has no {RESULT_HEADING!r} section.")
    result = read_stdin("Result")
    before_result = task.body.split(RESULT_HEADING)[0]
    task = Task(path=task.path, frontmatter_text=task.frontmatter_text, body=f"{before_result}{RESULT_HEADING}\n{result}\n")
    updates = {"status": STATUS_FOR_OUTCOME[args.outcome], "dateModified": now_timestamp()}
    if args.outcome == "done":
        updates["completedDate"] = f"{datetime.now():%Y-%m-%d}"
    update_frontmatter(task, updates)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)

    commands.add_parser("print-path", help="Print the tasks directory.").set_defaults(handler=command_print_path)

    create = commands.add_parser("create", help="Create an agent subtask; brief on stdin; prints its path.")
    create.add_argument("--title", required=True)
    create.add_argument("--parent", metavar="TASK", help="Task file stem this becomes a subtask of; any owner.")
    create.add_argument("--blocked-by", type=task_stem_list, action="extend", default=[], metavar="TASKS", help="Blocking task file stems, comma-separated or repeated.")
    create.set_defaults(handler=command_create)

    commands.add_parser("ready", help="List open agent subtasks whose blockers are done, as 'stem<TAB>title'.").set_defaults(handler=command_ready)

    edit = commands.add_parser("edit", help="Change an agent subtask's parent or blockers, mirroring `gh issue edit`.")
    edit.add_argument("task", help="Task file stem.")
    parent = edit.add_mutually_exclusive_group()
    parent.add_argument("--parent", metavar="TASK", help="Set the parent task, replacing any previous one.")
    parent.add_argument("--remove-parent", action="store_true", help="Remove the parent task.")
    edit.add_argument("--add-blocked-by", type=task_stem_list, action="extend", default=[], metavar="TASKS", help="Add blocking tasks, comma-separated or repeated.")
    edit.add_argument("--remove-blocked-by", type=task_stem_list, action="extend", default=[], metavar="TASKS", help="Remove blocking tasks, comma-separated or repeated.")
    edit.set_defaults(handler=command_edit)

    claim = commands.add_parser("claim", help="Mark a ready subtask in-progress for a thread.")
    claim.add_argument("task", help="Task file stem.")
    claim.add_argument("--thread", required=True, help="Id of the thread doing the work.")
    claim.set_defaults(handler=command_claim)

    finish = commands.add_parser("finish", help="Record the result (stdin) of an in-progress subtask.")
    finish.add_argument("task", help="Task file stem.")
    finish.add_argument("--outcome", choices=STATUS_FOR_OUTCOME, default="done", help="failed parks the task as paused for re-planning.")
    finish.set_defaults(handler=command_finish)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except TaskError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()

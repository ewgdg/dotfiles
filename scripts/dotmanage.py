#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SUPPORTED_OPERATIONS = {"update", "install", "import"}
PROFILE_HEADER_RE = re.compile(r'^Dotfile\(s\) for profile "([^"]+)":$')
DOTDROP_PHASE_SUMMARY_RE = re.compile(r"\s*(\d+) (?:file|dotfile)\(s\) (?:updated|installed)\.\s*")


@dataclass
class ParsedArgs:
    base_args: list[str] = field(default_factory=list)
    files_args: list[str] = field(default_factory=list)
    explicit_targets: list[str] = field(default_factory=list)
    key_mode: bool = False
    force_mode: bool = False
    remove_existing_mode: bool = False
    profile_from_args: str = ""
    config_path_from_args: str = ""
    update_ignore_patterns: list[str] = field(default_factory=list)


@dataclass
class BackupEntry:
    source_path: Path
    backup_path: Path
    original_existed: bool


@dataclass
class TemplateUpdateState:
    changed: bool = False
    skipped: bool = False


@dataclass
class PhaseExecutionResult:
    exit_code: int
    changed_count: int


class DotManager:
    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.dotdrop_cmd = shutil.which("dotdrop") or ""
        self.operation = ""
        self.command_args: list[str] = []
        self.parsed = ParsedArgs()
        self.resolved_config_path = ""
        self.repo_root = ""
        self.template_update_script = ""
        self.effective_profile = ""

        self.all_keys: list[str] = []
        self.all_dsts: list[str] = []
        self.source_by_key: dict[str, str] = {}
        self.destination_by_key: dict[str, str] = {}
        self.normalized_destination_by_key: dict[str, str] = {}
        self.effective_template_by_key: dict[str, int] = {}

        self.install_keys: list[str] = []
        self.regular_update_keys: list[str] = []
        self.template_update_keys: list[str] = []
        self.regular_update_key_set: set[str] = set()
        self.template_update_key_set: set[str] = set()
        self.scoped_update_key_set: set[str] = set()
        self.scoped_update_allowed_live_path_set: set[str] = set()

        self.declined_update_backup_dir: Path | None = None
        self.declined_update_backup_entries: list[BackupEntry] = []
        self.template_update_staging_dir: Path | None = None

        self.overall_exit_code = 0
        self.last_template_update = TemplateUpdateState()

    def run(self) -> int:
        if not self.dotdrop_cmd:
            print("dotdrop not found in PATH", file=sys.stderr)
            return 127

        if not self.argv:
            return self.run_passthrough([])

        first = self.argv[0]
        if first in SUPPORTED_OPERATIONS:
            self.operation = first
            self.command_args = self.argv[1:]
        else:
            return self.run_passthrough(self.argv)

        if self.operation == "import":
            return self.run_passthrough([self.operation, "-b", *self.command_args])

        self.parsed = self.parse_args(self.command_args)
        self.resolved_config_path = self.resolve_config_path()
        if not self.resolved_config_path:
            print(
                "unable to determine dotdrop config path; pass -c/--cfg or set DOTDROP_CONFIG",
                file=sys.stderr,
            )
            return 2

        self.repo_root = str(Path(self.resolved_config_path).parent)
        self.template_update_script = str(Path(self.repo_root) / "scripts" / "dotdrop_template_update.py")

        self.load_key_metadata()
        self.select_targets()

        if not self.parsed.explicit_targets and not self.parsed.force_mode:
            if not self.confirm_whole_profile_operation():
                return 1

        if self.is_update_operation:
            try:
                self.confirm_update_overwrite_targets()
                self.run_update_phases()
            finally:
                self.restore_declined_update_state()
            return self.overall_exit_code

        self.run_install_phases()
        return self.overall_exit_code

    def run_passthrough(self, args: list[str]) -> int:
        completed = subprocess.run([self.dotdrop_cmd, *args], check=False)
        return completed.returncode

    @property
    def is_update_operation(self) -> bool:
        return self.operation == "update"

    @property
    def is_install_operation(self) -> bool:
        return self.operation == "install"

    @staticmethod
    def operation_words(operation: str) -> tuple[str, str]:
        if operation == "install":
            return "Install", "installing"
        if operation == "update":
            return "Update", "updating"
        return operation.title(), operation

    def parse_args(self, args: list[str]) -> ParsedArgs:
        parsed = ParsedArgs()
        after_double_dash = False
        idx = 0
        while idx < len(args):
            arg = args[idx]
            if after_double_dash:
                parsed.explicit_targets.append(arg)
                idx += 1
                continue

            if arg == "--":
                after_double_dash = True
                idx += 1
                continue

            if arg in {"-k", "--key"}:
                if self.is_update_operation:
                    parsed.key_mode = True
                else:
                    parsed.base_args.append(arg)
                idx += 1
                continue

            if arg in {"-f", "--force"}:
                parsed.force_mode = True
                parsed.base_args.append(arg)
                idx += 1
                continue

            if arg in {"-R", "--remove-existing"}:
                parsed.remove_existing_mode = True
                parsed.base_args.append(arg)
                idx += 1
                continue

            if arg in {"-c", "--cfg", "-p", "--profile"}:
                if idx + 1 >= len(args):
                    print(f"missing value for {arg}", file=sys.stderr)
                    raise SystemExit(2)
                value = args[idx + 1]
                if arg in {"-p", "--profile"}:
                    parsed.profile_from_args = value
                else:
                    parsed.config_path_from_args = value
                parsed.base_args.extend([arg, value])
                parsed.files_args.extend([arg, value])
                idx += 2
                continue

            if arg.startswith("--cfg=") or arg.startswith("--profile="):
                if arg.startswith("--profile="):
                    parsed.profile_from_args = arg.split("=", 1)[1]
                else:
                    parsed.config_path_from_args = arg.split("=", 1)[1]
                parsed.base_args.append(arg)
                parsed.files_args.append(arg)
                idx += 1
                continue

            if arg in {"-V", "--verbose", "-b", "--no-banner"}:
                parsed.base_args.append(arg)
                parsed.files_args.append(arg)
                idx += 1
                continue

            if arg in {"-w", "--workers"}:
                if idx + 1 >= len(args):
                    print(f"missing value for {arg}", file=sys.stderr)
                    raise SystemExit(2)
                parsed.base_args.extend([arg, args[idx + 1]])
                idx += 2
                continue

            if arg in {"-i", "--ignore"}:
                if idx + 1 >= len(args):
                    print(f"missing value for {arg}", file=sys.stderr)
                    raise SystemExit(2)
                value = args[idx + 1]
                parsed.update_ignore_patterns.append(value)
                parsed.base_args.extend([arg, value])
                idx += 2
                continue

            if arg.startswith("--workers="):
                parsed.base_args.append(arg)
                idx += 1
                continue

            if arg.startswith("--ignore="):
                parsed.update_ignore_patterns.append(arg.split("=", 1)[1])
                parsed.base_args.append(arg)
                idx += 1
                continue

            if arg.startswith("-"):
                if arg == "--force" or (not arg.startswith("--") and "f" in arg[1:]):
                    parsed.force_mode = True
                parsed.base_args.append(arg)
                idx += 1
                continue

            parsed.explicit_targets.append(arg)
            idx += 1

        return parsed

    def resolve_config_path(self) -> str:
        if self.parsed.config_path_from_args:
            return os.path.abspath(os.path.expanduser(self.parsed.config_path_from_args))

        if os.environ.get("DOTDROP_CONFIG"):
            return os.path.abspath(os.path.expanduser(os.environ["DOTDROP_CONFIG"]))

        for candidate in ("config.yaml", "config.toml"):
            candidate_path = Path.cwd() / candidate
            if candidate_path.is_file():
                return str(candidate_path)

        return ""

    def resolve_effective_profile(self) -> str:
        if self.parsed.profile_from_args:
            return self.parsed.profile_from_args

        completed = self.capture_or_exit(
            [self.dotdrop_cmd, "files", "-b", *self.parsed.files_args],
            stderr_to_stdout=True,
        )
        for line in completed.stdout.splitlines():
            match = PROFILE_HEADER_RE.match(line)
            if match:
                return match.group(1)
        return ""

    def load_key_metadata(self) -> None:
        dotfiles_output = self.capture_or_exit(
            [self.dotdrop_cmd, "files", "-G", *self.parsed.files_args]
        ).stdout
        self.effective_profile = self.resolve_effective_profile()

        for line in dotfiles_output.splitlines():
            if ",dst:" not in line:
                continue
            key, _, remainder = line.partition(",dst:")
            dst, _, _ = remainder.partition(",")
            src = ""
            if ",src:" in line:
                _, _, src_remainder = line.partition(",src:")
                src, _, _ = src_remainder.partition(",")
            self.all_keys.append(key)
            self.all_dsts.append(dst)
            self.source_by_key[key] = src
            self.destination_by_key[key] = dst
            self.normalized_destination_by_key[key] = self.normalize_target_path(dst)

        if self.operation != "update":
            return

        if not self.effective_profile:
            print("unable to determine active dotdrop profile", file=sys.stderr)
            raise SystemExit(2)

        detail_output = self.capture_or_exit(
            [self.dotdrop_cmd, "detail", "-b", *self.parsed.files_args, *self.all_keys]
        ).stdout
        detail_key = ""
        for detail_line in detail_output.splitlines():
            if ' (dst: "' in detail_line and not detail_line.startswith(" "):
                detail_key = detail_line.split(" (dst: ", 1)[0]
                self.effective_template_by_key[detail_key] = 0
                continue
            if detail_key and "(template:yes)" in detail_line:
                self.effective_template_by_key[detail_key] = 1

    def select_targets(self) -> None:
        if self.parsed.explicit_targets:
            if self.is_update_operation and not self.parsed.key_mode:
                self.select_explicit_update_targets()
            else:
                self.select_explicit_keys()
            return

        for key_name, key_dst in zip(self.all_keys, self.all_dsts):
            self.append_split_key(key_name, key_dst, self.source_by_key.get(key_name, ""))

    def select_explicit_update_targets(self) -> None:
        for requested_path in self.parsed.explicit_targets:
            normalized_requested_path = self.normalize_target_path(requested_path)
            matched_key = self.find_matching_update_key_for_path(normalized_requested_path)
            if not matched_key:
                print(
                    f"no tracked dotdrop key matches update target '{requested_path}' for current profile/config",
                    file=sys.stderr,
                )
                raise SystemExit(2)

            if self.is_templated_key(matched_key) and normalized_requested_path != self.normalized_destination_by_key[matched_key]:
                print(
                    f"scoped updates inside templated directory key '{matched_key}' are not supported",
                    file=sys.stderr,
                )
                raise SystemExit(2)

            self.record_effective_update_key(matched_key)
            if normalized_requested_path != self.normalized_destination_by_key[matched_key]:
                self.record_scoped_update_target(matched_key, normalized_requested_path)

    def select_explicit_keys(self) -> None:
        for requested_key in self.parsed.explicit_targets:
            if requested_key not in self.destination_by_key:
                print(
                    f"unknown dotdrop key '{requested_key}' for current profile/config",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            self.append_split_key(
                requested_key,
                self.destination_by_key[requested_key],
                self.source_by_key.get(requested_key, ""),
            )

    def confirm_whole_profile_operation(self) -> bool:
        profile = self.effective_profile or "<unknown>"
        operation_word, _ = self.operation_words(self.operation)
        prompt = f'{operation_word} all dotfiles for profile "{profile}" [y/N] ? '
        if not sys.stdin.isatty():
            print(
                "confirmation required but no interactive tty is available; pass explicit targets to skip prompt",
                file=sys.stderr,
            )
            raise SystemExit(2)
        answer = self.prompt(prompt)
        if answer.lower() in {"y", "yes"}:
            return True
        print("aborted", file=sys.stderr)
        return False

    def collect_update_change_pairs(self) -> list[tuple[str, str]]:
        if not self.regular_update_keys:
            return []

        dry_run_call = [
            self.dotdrop_cmd,
            "update",
            "-b",
            "-d",
            "-f",
            *self.parsed.base_args,
            "-k",
            *self.regular_update_keys,
        ]
        completed = subprocess.run(
            dry_run_call,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return []

        overwrite_pairs: list[tuple[str, str]] = []
        for raw_line in completed.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("[DRY] would update content of "):
                payload = self.trim_trailing_whitespace(line.removeprefix("[DRY] would update content of "))
                source_file_path, separator, live_file_path = payload.partition(" from ")
                if not separator:
                    continue
                source_file_path = self.trim_trailing_whitespace(source_file_path)
                live_file_path = self.trim_trailing_whitespace(live_file_path)
                if self.paths_are_identical_if_present(source_file_path, live_file_path):
                    continue
                overwrite_pairs.append((source_file_path, live_file_path))
                continue

            payload = ""
            if line.startswith("[DRY] would cp -r "):
                payload = line.removeprefix("[DRY] would cp -r ")
            elif line.startswith("[DRY] would cp "):
                payload = line.removeprefix("[DRY] would cp ")
            else:
                continue

            payload = self.trim_trailing_whitespace(payload)
            if " " not in payload:
                continue
            live_file_path, source_file_path = payload.rsplit(" ", 1)
            live_file_path = self.trim_trailing_whitespace(live_file_path)
            source_file_path = self.trim_trailing_whitespace(source_file_path)
            if not source_file_path or not live_file_path:
                continue
            if self.paths_are_identical_if_present(source_file_path, live_file_path):
                continue
            overwrite_pairs.append((source_file_path, live_file_path))

        return sorted(overwrite_pairs)

    def confirm_update_overwrite_targets(self) -> None:
        if not self.is_update_operation:
            return

        overwrite_pairs = self.collect_update_change_pairs()
        if not overwrite_pairs:
            return

        for source_file_path, live_file_path in overwrite_pairs:
            normalized_live_file_path = self.normalize_target_path(live_file_path)
            candidate_key = self.find_matching_update_key_for_path(normalized_live_file_path)

            if (
                candidate_key
                and candidate_key in self.scoped_update_key_set
                and normalized_live_file_path not in self.scoped_update_allowed_live_path_set
            ):
                self.backup_declined_update_path(Path(source_file_path), Path(live_file_path))
                continue

            if self.parsed.force_mode or not sys.stdin.isatty():
                continue

            source_path = Path(source_file_path)
            live_path = Path(live_file_path)
            if source_path.exists():
                answer = self.prompt(f'overwrite dotfiles path "{source_file_path}" [y/N] ? ')
            else:
                answer = self.prompt(
                    f'import live path into dotfiles "{source_file_path}" from "{live_file_path}" [y/N] ? '
                )

            if answer.lower() not in {"y", "yes"}:
                self.backup_declined_update_path(source_path, live_path)

    def print_phase_header(self, header_text: str) -> None:
        if sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb":
            print(f"\n\033[1;34m==>\033[0m \033[1m{header_text}\033[0m\n")
            return
        print(f"\n==> {header_text}\n")

    def system_phase_needs_run(self, operation_targets: list[str]) -> bool:
        if not operation_targets:
            return False

        compare_call = [self.dotdrop_cmd, "compare", "-L", "-b", *self.parsed.files_args]
        for focus_target in operation_targets:
            compare_path = self.normalized_destination_by_key.get(focus_target, focus_target)
            compare_call.extend(["-C", compare_path])

        compare_completed = subprocess.run(
            compare_call,
            check=False,
            capture_output=True,
            text=True,
        )
        compare_output = compare_completed.stdout + compare_completed.stderr
        if compare_completed.returncode != 0:
            return True

        for line in compare_output.splitlines():
            if not line or line.startswith(" "):
                continue
            if line.endswith(" dotfile(s) compared."):
                continue
            return True

        if self.operation != "install" or not self.parsed.remove_existing_mode:
            return False

        dry_run_call = [
            self.dotdrop_cmd,
            "install",
            "-b",
            "-d",
            *self.parsed.base_args,
            *operation_targets,
        ]
        dry_run_completed = subprocess.run(
            dry_run_call,
            check=False,
            capture_output=True,
            text=True,
        )
        dry_run_output = dry_run_completed.stdout + dry_run_completed.stderr
        if dry_run_completed.returncode != 0:
            return True

        for line in dry_run_output.splitlines():
            if line.startswith("[DRY] would remove "):
                return True
        return False

    @staticmethod
    def parse_phase_changed_count(output_text: str) -> int:
        for line in output_text.splitlines():
            match = DOTDROP_PHASE_SUMMARY_RE.fullmatch(line)
            if match:
                return int(match.group(1))
        return 0

    @classmethod
    def print_phase_body_output(cls, output_text: str, *, stream: object) -> None:
        kept_lines: list[str] = []
        for line in output_text.splitlines():
            if DOTDROP_PHASE_SUMMARY_RE.fullmatch(line):
                continue
            kept_lines.append(line)

        if not kept_lines:
            return

        text = "\n".join(kept_lines)
        if output_text.endswith("\n"):
            text += "\n"
        stream.write(text)

    def run_operation_for_targets(self, run_with_sudo: bool, operation_targets: list[str]) -> PhaseExecutionResult:
        dotdrop_call = [self.dotdrop_cmd, self.operation, "-b", *self.parsed.base_args]
        if self.is_update_operation:
            dotdrop_call.extend(["-f", "-k"])
        dotdrop_call.extend(operation_targets)

        if run_with_sudo:
            command = ["sudo", "env", f"PATH={os.environ.get('PATH', '')}"]
            if os.environ.get("DOTDROP_CONFIG"):
                command.append(f"DOTDROP_CONFIG={os.environ['DOTDROP_CONFIG']}")
            command.extend(dotdrop_call)
        else:
            command = dotdrop_call

        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.stdout:
            self.print_phase_body_output(completed.stdout, stream=sys.stdout)
        if completed.stderr:
            self.print_phase_body_output(completed.stderr, stream=sys.stderr)

        return PhaseExecutionResult(
            exit_code=completed.returncode,
            changed_count=self.parse_phase_changed_count(completed.stdout),
        )

    @staticmethod
    def print_phase_summary(processed_count: int, updated_count: int, failed_count: int) -> None:
        print(f"{processed_count} file(s) processed, {updated_count} updated, {failed_count} failed")

    def split_keys_by_required_read_privilege(self, keys: list[str]) -> tuple[list[str], list[str]]:
        non_privileged: list[str] = []
        privileged: list[str] = []
        for key in keys:
            target_dst = self.normalized_destination_by_key[key]
            if self.path_needs_privileged_read(target_dst):
                privileged.append(key)
            else:
                non_privileged.append(key)
        return non_privileged, privileged

    def split_keys_by_required_write_privilege(self, keys: list[str]) -> tuple[list[str], list[str]]:
        non_privileged: list[str] = []
        privileged: list[str] = []
        for key in keys:
            target_dst = self.normalized_destination_by_key[key]
            if self.path_needs_privileged_write(target_dst):
                privileged.append(key)
            else:
                non_privileged.append(key)
        return non_privileged, privileged

    def run_phase_operation(
        self, phase_name: str, run_with_sudo: bool, phase_targets: list[str]
    ) -> PhaseExecutionResult:
        if not phase_targets:
            return PhaseExecutionResult(exit_code=0, changed_count=0)

        phase_result = self.run_operation_for_targets(run_with_sudo, phase_targets)
        if phase_result.exit_code != 0:
            print(f"{phase_name} phase exited with status {phase_result.exit_code}", file=sys.stderr)
            if self.overall_exit_code == 0:
                self.overall_exit_code = phase_result.exit_code
        return phase_result

    def run_named_phase(self, phase_name: str, run_with_sudo: bool, phase_targets: list[str]) -> None:
        if not phase_targets:
            return

        _, operation_verb = self.operation_words(self.operation)
        self.print_phase_header(f"{operation_verb} {phase_name}")
        should_preflight = self.is_install_operation and run_with_sudo
        if should_preflight and not self.system_phase_needs_run(phase_targets):
            self.print_phase_summary(len(phase_targets), 0, 0)
            return

        phase_result = self.run_phase_operation(phase_name, run_with_sudo, phase_targets)
        failed_count = 1 if phase_result.exit_code != 0 else 0
        self.print_phase_summary(len(phase_targets), phase_result.changed_count, failed_count)

    def prepare_template_update_for_key(self, key_name: str) -> tuple[int, str, str]:
        self.last_template_update = TemplateUpdateState()

        target_src = self.source_by_key[key_name]
        target_dst = self.normalized_destination_by_key.get(key_name, self.destination_by_key[key_name])
        if not Path(target_src).is_file():
            print(
                f"template-aware update only supports file sources; key '{key_name}' uses '{target_src}'",
                file=sys.stderr,
            )
            return 2, "", ""

        if not os.access(self.template_update_script, os.R_OK):
            print(f"template update helper not found at {self.template_update_script}", file=sys.stderr)
            return 2, "", ""

        if not Path(target_dst).exists():
            print(f"live destination for key '{key_name}' not found at '{target_dst}'", file=sys.stderr)
            return 1, "", ""

        staging_dir = self.ensure_template_update_staging_dir()
        fd, staged_output_file = tempfile.mkstemp(prefix="template-update.", dir=staging_dir)
        os.close(fd)

        helper_command = [
            "uv",
            "run",
            self.template_update_script,
            target_src,
            target_dst,
            staged_output_file,
            "--json",
        ]
        stdout_text: str
        stderr_text: str

        if self.path_needs_privileged_read(target_dst):
            cat_completed = subprocess.run(
                ["sudo", "cat", target_dst],
                check=False,
                capture_output=True,
            )
            if cat_completed.returncode != 0:
                if cat_completed.stderr:
                    sys.stderr.buffer.write(cat_completed.stderr)
                return cat_completed.returncode, "", ""
            helper_command[4] = "-"
            helper_completed = subprocess.run(
                helper_command,
                check=False,
                input=cat_completed.stdout,
                capture_output=True,
            )
            stdout_text = helper_completed.stdout.decode("utf-8", errors="replace")
            stderr_text = helper_completed.stderr.decode("utf-8", errors="replace")
        else:
            helper_completed = subprocess.run(
                helper_command,
                check=False,
                capture_output=True,
                text=True,
            )
            stdout_text = helper_completed.stdout
            stderr_text = helper_completed.stderr

        if helper_completed.returncode != 0:
            if stdout_text:
                sys.stdout.write(stdout_text)
            if stderr_text:
                sys.stderr.write(stderr_text)
            return helper_completed.returncode, "", ""

        helper_output_compact = stdout_text.replace("\n", "")
        if '"changed":true' in helper_output_compact:
            self.last_template_update.changed = True
        elif '"changed":false' in helper_output_compact:
            self.last_template_update.changed = False
        else:
            print(
                f"unexpected template update status for key '{key_name}': {stdout_text}",
                file=sys.stderr,
            )
            return 2, "", ""

        return 0, staged_output_file, helper_output_compact

    def confirm_template_update_overwrite(self, source_file_path: str) -> bool:
        if not self.is_update_operation or self.parsed.force_mode or not self.last_template_update.changed:
            return True
        if not sys.stdin.isatty():
            return True
        answer = self.prompt(f'overwrite template file "{source_file_path}" [y/N] ? ')
        if answer.lower() in {"y", "yes"}:
            return True
        self.last_template_update.changed = False
        self.last_template_update.skipped = True
        return False

    def print_template_update_summary(self, key_name: str, helper_output_compact: str) -> None:
        target_src = self.source_by_key[key_name]

        def extract(metric: str) -> str:
            match = re.search(rf'"{metric}":([0-9]+)', helper_output_compact)
            return match.group(1) if match else "?"

        print(
            "merged template update: "
            f"key={key_name} "
            f"matched_lines={extract('matched_lines')} "
            f"whole_blocks={extract('whole_blocks')} "
            f"partial_blocks={extract('partial_blocks')} "
            f"conflict_blocks={extract('conflict_blocks')} "
            f"unchanged_blocks={extract('unchanged_blocks')} "
            f"output={target_src}"
        )

    def run_template_update_for_key(self, key_name: str) -> int:
        prepare_exit_code, staged_output_path, helper_output_compact = self.prepare_template_update_for_key(key_name)
        if prepare_exit_code != 0:
            return prepare_exit_code

        if not self.last_template_update.changed:
            return 0

        target_src = self.source_by_key[key_name]
        if not self.confirm_template_update_overwrite(target_src):
            print(f"skipped template update: key={key_name} output={target_src}")
            return 0

        shutil.copy2(staged_output_path, target_src)
        self.print_template_update_summary(key_name, helper_output_compact)
        return 0

    def run_template_phase(self, phase_name: str, template_keys: list[str]) -> None:
        if not template_keys:
            return

        _, operation_verb = self.operation_words(self.operation)
        self.print_phase_header(f"{operation_verb} {phase_name}")

        processed_count = len(template_keys)
        changed_count = 0
        failed_count = 0

        for key_name in template_keys:
            self.last_template_update = TemplateUpdateState()
            phase_exit_code = self.run_template_update_for_key(key_name)
            if phase_exit_code != 0:
                failed_count += 1
                print(f"{phase_name} template update failed for key '{key_name}'", file=sys.stderr)
                if self.overall_exit_code == 0:
                    self.overall_exit_code = phase_exit_code
                continue

            if self.last_template_update.changed:
                changed_count += 1

        self.print_phase_summary(processed_count, changed_count, failed_count)

    def run_install_phases(self) -> None:
        non_privileged_install_keys, privileged_install_keys = self.split_keys_by_required_write_privilege(
            self.install_keys
        )
        self.run_named_phase("dotfiles", False, non_privileged_install_keys)
        self.run_named_phase("dotfiles (sudo)", True, privileged_install_keys)

    def run_update_phases(self) -> None:
        non_privileged_update_keys, privileged_update_keys = self.split_keys_by_required_read_privilege(
            self.regular_update_keys
        )
        non_privileged_template_keys, privileged_template_keys = self.split_keys_by_required_read_privilege(
            self.template_update_keys
        )
        self.run_named_phase("dotfiles", False, non_privileged_update_keys)
        self.run_named_phase("dotfiles (sudo)", True, privileged_update_keys)
        self.run_template_phase("dotfiles (template-aware)", non_privileged_template_keys)
        self.run_template_phase("dotfiles (template-aware, sudo)", privileged_template_keys)

    def record_regular_update_key(self, target_key: str) -> None:
        if target_key in self.regular_update_key_set:
            return
        self.regular_update_keys.append(target_key)
        self.regular_update_key_set.add(target_key)

    def record_template_update_key(self, target_key: str) -> None:
        if target_key in self.template_update_key_set:
            return
        self.template_update_keys.append(target_key)
        self.template_update_key_set.add(target_key)

    def record_scoped_update_target(self, target_key: str, live_path: str) -> None:
        self.scoped_update_key_set.add(target_key)
        self.scoped_update_allowed_live_path_set.add(live_path)

    def append_split_key(self, split_key: str, split_dst: str, split_src: str) -> None:
        if self.is_update_operation and self.parsed.update_ignore_patterns:
            if self.key_is_fully_ignored_for_update(split_dst, split_src, self.parsed.update_ignore_patterns):
                return

        if self.is_update_operation:
            self.record_effective_update_key(split_key)
            return

        self.install_keys.append(split_key)

    def is_templated_key(self, key_name: str) -> bool:
        return self.effective_template_by_key.get(key_name, 0) == 1

    def record_effective_update_key(self, key_name: str) -> None:
        if self.is_templated_key(key_name):
            self.record_template_update_key(key_name)
            return
        self.record_regular_update_key(key_name)

    def find_matching_update_key_for_path(self, requested_path: str) -> str:
        matched_key = ""
        matched_length = 0
        for known_key in self.all_keys:
            known_destination = self.normalized_destination_by_key[known_key]
            if requested_path == known_destination:
                return known_key
            if requested_path.startswith(known_destination + os.sep) and len(known_destination) > matched_length:
                matched_key = known_key
                matched_length = len(known_destination)
        return matched_key

    def ensure_declined_update_backup_dir(self) -> Path:
        if self.declined_update_backup_dir is None:
            self.declined_update_backup_dir = Path(tempfile.mkdtemp())
        return self.declined_update_backup_dir

    def ensure_template_update_staging_dir(self) -> str:
        if self.template_update_staging_dir is None:
            self.template_update_staging_dir = Path(tempfile.mkdtemp())
        return str(self.template_update_staging_dir)

    def backup_declined_update_path(self, source_path: Path, live_path: Path) -> None:
        backup_dir = self.ensure_declined_update_backup_dir()
        backup_path = backup_dir / str(len(self.declined_update_backup_entries))
        original_existed = source_path.exists()
        if original_existed:
            self.copy_path_preserving_metadata(source_path, backup_path)
        self.copy_path_preserving_metadata(live_path, source_path)
        self.declined_update_backup_entries.append(
            BackupEntry(source_path=source_path, backup_path=backup_path, original_existed=original_existed)
        )

    def restore_declined_update_paths(self) -> None:
        for entry in self.declined_update_backup_entries:
            if entry.original_existed:
                self.copy_path_preserving_metadata(entry.backup_path, entry.source_path)
                continue
            if entry.source_path.exists():
                self.remove_path(entry.source_path)

    def cleanup_declined_update_backups(self) -> None:
        if self.declined_update_backup_dir and self.declined_update_backup_dir.exists():
            shutil.rmtree(self.declined_update_backup_dir)
        self.declined_update_backup_dir = None
        self.declined_update_backup_entries = []

    def cleanup_template_update_staging_dir(self) -> None:
        if self.template_update_staging_dir and self.template_update_staging_dir.exists():
            shutil.rmtree(self.template_update_staging_dir)
        self.template_update_staging_dir = None

    def restore_declined_update_state(self) -> None:
        self.restore_declined_update_paths()
        self.cleanup_declined_update_backups()
        self.cleanup_template_update_staging_dir()

    def capture_or_exit(
        self,
        command: list[str],
        *,
        stderr_to_stdout: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if stderr_to_stdout else subprocess.PIPE,
        )
        if completed.returncode == 0:
            return completed

        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)

    @staticmethod
    def prompt(message: str) -> str:
        sys.stdout.write(message)
        sys.stdout.flush()
        answer = sys.stdin.readline()
        return answer.strip()

    @staticmethod
    def normalize_target_path(raw_path: str) -> str:
        return os.path.abspath(os.path.expanduser(raw_path))

    @staticmethod
    def trim_trailing_whitespace(value: str) -> str:
        return value.rstrip()

    @classmethod
    def copy_path_preserving_metadata(cls, source_path: Path, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        source_mode = source_path.lstat().st_mode
        if stat.S_ISDIR(source_mode):
            if target_path.exists():
                cls.remove_path(target_path)
            target_path.mkdir(parents=True, exist_ok=True)
            for entry in source_path.iterdir():
                # Live trees like ssh-agent directories can contain sockets that cannot be copied into dotfiles.
                if cls.path_is_unsupported_special_file(entry):
                    continue
                cls.copy_path_preserving_metadata(entry, target_path / entry.name)
            shutil.copystat(source_path, target_path, follow_symlinks=False)
            return
        if cls.path_is_unsupported_special_file(source_path):
            return
        if target_path.exists() and target_path.is_dir():
            cls.remove_path(target_path)
        shutil.copy2(source_path, target_path, follow_symlinks=False)

    @staticmethod
    def path_is_unsupported_special_file(path: Path) -> bool:
        path_mode = path.lstat().st_mode
        return not (
            stat.S_ISDIR(path_mode)
            or stat.S_ISREG(path_mode)
            or stat.S_ISLNK(path_mode)
        )

    @classmethod
    def remove_path(cls, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()

    @classmethod
    def paths_are_identical_if_present(cls, source_path: str, target_path: str) -> bool:
        source = Path(source_path)
        target = Path(target_path)
        if not source.exists() or not target.exists():
            return False
        return cls.paths_are_identical(source, target)

    @classmethod
    def paths_are_identical(cls, source_path: Path, target_path: Path) -> bool:
        if source_path.is_file() and target_path.is_file():
            return source_path.read_bytes() == target_path.read_bytes()

        if source_path.is_dir() and target_path.is_dir():
            source_entries = sorted(entry.name for entry in source_path.iterdir())
            target_entries = sorted(entry.name for entry in target_path.iterdir())
            if source_entries != target_entries:
                return False
            for name in source_entries:
                if not cls.paths_are_identical(source_path / name, target_path / name):
                    return False
            return True

        return False

    @staticmethod
    def matches_ignore_pattern(path: str, pattern: str) -> bool:
        current = path
        while True:
            if Path(current).match(pattern):
                return True
            if current == os.sep:
                break
            parent = str(Path(current).parent)
            if parent == current:
                break
            current = parent
        return False

    @classmethod
    def path_is_ignored(cls, path: str, patterns: Iterable[str]) -> bool:
        positive_match_count = 0
        negative_patterns: list[str] = []
        for pattern in patterns:
            if pattern.startswith("!"):
                negative_patterns.append(pattern[1:])
                continue
            if cls.matches_ignore_pattern(path, pattern):
                positive_match_count += 1

        if positive_match_count < 1:
            return False

        for pattern in negative_patterns:
            if cls.matches_ignore_pattern(path, pattern) and positive_match_count > 0:
                positive_match_count -= 1

        if positive_match_count < 1:
            return False

        path_obj = Path(path)
        if negative_patterns and (path_obj.is_dir() or not path_obj.exists()):
            return False
        return True

    @classmethod
    def key_is_fully_ignored_for_update(
        cls,
        key_dst: str,
        key_src: str,
        raw_patterns: Iterable[str],
    ) -> bool:
        prefixes = [key_dst]
        if key_src:
            prefixes.append(key_src)

        absolute_patterns: list[str] = []
        for raw_pattern in raw_patterns:
            pattern = raw_pattern
            is_negative = False
            if pattern.startswith("!"):
                is_negative = True
                pattern = pattern[1:]

            if pattern.startswith("/"):
                pass
            elif "*" in pattern and (pattern.startswith("*") or pattern.startswith("/")):
                pass
            else:
                for prefix in prefixes:
                    absolute_patterns.append(f"!{prefix}/{pattern}" if is_negative else f"{prefix}/{pattern}")
                continue

            absolute_patterns.append(f"!{pattern}" if is_negative else pattern)

        if cls.path_is_ignored(key_dst, absolute_patterns):
            return True
        if key_src and cls.path_is_ignored(key_src, absolute_patterns):
            return True
        return False

    @staticmethod
    def path_needs_privileged_read(target_path: str) -> bool:
        path = Path(target_path)
        if not path.exists():
            return False
        if path.is_dir():
            return not (os.access(path, os.R_OK) and os.access(path, os.X_OK))
        return not os.access(path, os.R_OK)

    @staticmethod
    def path_needs_privileged_write(target_path: str) -> bool:
        path = Path(target_path)
        probe = path
        if probe.exists():
            if probe.is_dir():
                return not (os.access(probe, os.W_OK) and os.access(probe, os.X_OK))
            return not os.access(probe, os.W_OK)

        while not probe.exists() and str(probe) != os.sep:
            probe = probe.parent
        if not probe.is_dir():
            return True
        return not (os.access(probe, os.W_OK) and os.access(probe, os.X_OK))


def main() -> int:
    try:
        return DotManager(sys.argv[1:]).run()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        return code


if __name__ == "__main__":
    raise SystemExit(main())

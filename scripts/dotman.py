#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import selectors
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, TextIO

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


SUPPORTED_OPERATIONS = {"update", "install", "import"}
PROFILE_HEADER_RE = re.compile(r'^Dotfile\(s\) for profile "([^"]+)":$')
DOTDROP_PHASE_SUMMARY_RE = re.compile(r"\s*(\d+) (?:file|dotfile)\(s\) (?:updated|installed)\.\s*")
DOTDROP_TEMPLATE_INCLUDE_RE = re.compile(r"{%@@\s*include\b")
INTERRUPTED_EXIT_CODE = 130
ANSI_RESET = "\033[0m"
DEFAULT_PROFILE_FILENAME = "default-profile"
DOTMAN_STATE_DIR_NAME = "dotman"


@dataclass
class ParsedArgs:
    base_args: list[str] = field(default_factory=list)
    explicit_targets: list[str] = field(default_factory=list)
    key_mode: bool = False
    force_mode: bool = False
    remove_existing_mode: bool = False
    profile_from_args: str = ""
    profile_was_explicitly_selected: bool = False
    config_path_from_args: str = ""
    update_ignore_patterns: list[str] = field(default_factory=list)
@dataclass
class BackupEntry:
    source_path: Path
    backup_path: Path
    original_existed: bool


@dataclass(frozen=True)
class PreviewTransform:
    input_path: Path
    output_path: Path
    command: tuple[str, ...]
    output_index: int


@dataclass(frozen=True)
class UpdateChange:
    source_path: Path
    live_path: Path
    preview_transform: PreviewTransform | None = None


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
        self.resolved_profile = ""

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
        if self.argv and self.argv[0] == "default":
            return self.run_default_subcommand(self.argv[1:])

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

        self.resolved_profile = self.resolve_profile()
        if not self.resolved_profile:
            picked = self.pick_profile_interactive()
            if not picked:
                print(
                    "unable to determine active dotdrop profile; "
                    "run 'dotman profiles' to list available profiles",
                    file=sys.stderr,
                )
                return 2
            self.resolved_profile = picked
            self.parsed.profile_from_args = picked
            self.parsed.profile_was_explicitly_selected = True
            print(
                f"tip: run 'dotman default {self.resolved_profile}' to save as default",
                file=sys.stderr,
            )
        dotfiles_output = self.load_dotfiles_output()
        self.load_key_metadata(dotfiles_output)
        self.select_targets()

        if not self.parsed.explicit_targets and not self.parsed.force_mode:
            if self.parsed.profile_was_explicitly_selected:
                self.log_profile_selection()
            elif not self.confirm_whole_profile_operation():
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

    def run_default_subcommand(self, args: list[str]) -> int:
        state_dir = get_dotman_state_dir()

        if not args:
            current = read_default_profile(state_dir)
            if current:
                print(current)
            else:
                print("no default profile set", file=sys.stderr)
            return 0

        if args[0] == "--unset":
            unset_default_profile(state_dir)
            print("default profile unset", file=sys.stderr)
            return 0

        profile_name = args[0]
        write_default_profile(state_dir, profile_name)
        print(f'default profile set to "{profile_name}"', file=sys.stderr)
        return 0

    def pick_profile_interactive(self) -> str:
        if not sys.stdin.isatty():
            return ""

        fzf = shutil.which("fzf")
        if not fzf:
            print(
                "install fzf to enable interactive profile selection", file=sys.stderr
            )
            return ""

        profiles = parse_profiles_from_config(self.resolved_config_path)
        if not profiles:
            if yaml is None:
                print(
                    "install pyyaml to enable interactive profile selection",
                    file=sys.stderr,
                )
            return ""

        ranked = rank_profiles(profiles)
        fzf_input = "\n".join(ranked)

        try:
            completed = subprocess.run(
                [
                    fzf,
                    "--prompt",
                    "profile> ",
                    "--height",
                    "~40%",
                    "--header",
                    "Select a profile:",
                ],
                input=fzf_input,
                check=False,
                capture_output=True,
                text=True,
            )
        except (OSError, KeyboardInterrupt):
            return ""

        if completed.returncode != 0:
            return ""

        return completed.stdout.strip()

    @property
    def is_update_operation(self) -> bool:
        return self.operation == "update"

    @property
    def is_install_operation(self) -> bool:
        return self.operation == "install"

    @property
    def metadata_args(self) -> list[str]:
        args: list[str] = []
        if self.resolved_config_path:
            args.append(f"--cfg={self.resolved_config_path}")

        profile = self.resolved_profile
        if profile:
            args.append(f"--profile={profile}")

        return args

    @staticmethod
    def operation_words(operation: str) -> tuple[str, str]:
        if operation == "install":
            return "Install", "installing"
        if operation == "update":
            return "Update", "updating"
        return operation.title(), operation

    def parse_args(self, args: list[str]) -> ParsedArgs:
        # Split on '--' first: everything after it is a literal target, not a flag.
        if "--" in args:
            sep_idx = args.index("--")
            flag_args = args[:sep_idx]
            literal_targets = args[sep_idx + 1 :]
        else:
            flag_args = args
            literal_targets = []

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("-k", "--key", action="store_true")
        parser.add_argument("-f", "--force", action="store_true")
        parser.add_argument(
            "-R", "--remove-existing", dest="remove_existing", action="store_true"
        )
        parser.add_argument("-p", "--profile", default="")
        parser.add_argument("-c", "--cfg", default="")
        parser.add_argument("-V", "--verbose", action="store_true")
        parser.add_argument("-b", "--no-banner", dest="no_banner", action="store_true")
        parser.add_argument("-w", "--workers", default="")
        parser.add_argument("-i", "--ignore", action="append", default=[])

        namespace, remaining = parser.parse_known_args(flag_args)

        # parse_known_args puts both unrecognized flags and positional args in
        # remaining. Split them: flags are forwarded to dotdrop; positionals
        # become explicit targets (same semantics as the previous manual loop).
        positional_targets = [a for a in remaining if not a.startswith("-")]
        unknown_flags = [a for a in remaining if a.startswith("-")]

        parsed = ParsedArgs()

        # -k/--key is a dotman-only flag in update mode. In other operations,
        # pass it through to dotdrop unchanged.
        if namespace.key:
            if self.is_update_operation:
                parsed.key_mode = True
            else:
                unknown_flags.insert(0, "-k")

        parsed.force_mode = namespace.force
        parsed.remove_existing_mode = namespace.remove_existing
        parsed.update_ignore_patterns = list(namespace.ignore)
        parsed.explicit_targets = positional_targets + literal_targets

        if namespace.profile:
            parsed.profile_from_args = namespace.profile
            parsed.profile_was_explicitly_selected = True

        if namespace.cfg:
            parsed.config_path_from_args = namespace.cfg

        # Reconstruct base_args for dotdrop. Valued options are emitted as
        # --opt=VALUE (single tokens) so files_args can filter unambiguously
        # without also having to grab the adjacent value token.
        base_args: list[str] = []
        if namespace.force:
            base_args.append("-f")
        if namespace.remove_existing:
            base_args.append("-R")
        if namespace.verbose:
            base_args.append("-V")
        if namespace.no_banner:
            base_args.append("-b")
        if namespace.workers:
            base_args.append(f"--workers={namespace.workers}")
        for pattern in namespace.ignore:
            base_args.append(f"--ignore={pattern}")
        base_args.extend(unknown_flags)

        parsed.base_args = base_args
        return parsed

    def resolve_config_path(self) -> str:
        if self.parsed.config_path_from_args:
            return os.path.abspath(
                os.path.expanduser(self.parsed.config_path_from_args)
            )

        if os.environ.get("DOTDROP_CONFIG"):
            return os.path.abspath(os.path.expanduser(os.environ["DOTDROP_CONFIG"]))

        for candidate in ("config.yaml", "config.toml"):
            candidate_path = Path.cwd() / candidate
            if candidate_path.is_file():
                return str(candidate_path)

        return ""

    def load_dotfiles_output(self) -> str:
        return self.capture_or_exit(
            [self.dotdrop_cmd, "files", "-b", "-G", *self.metadata_args],
            stderr_to_stdout=True,
        ).stdout

    def resolve_profile_from_env(self) -> str:
        return os.environ.get("DOTDROP_PROFILE", "").strip()

    def resolve_profile(self) -> str:
        if self.parsed.profile_from_args:
            return self.parsed.profile_from_args

        env_profile = self.resolve_profile_from_env()
        if env_profile:
            return env_profile

        stored = read_default_profile(get_dotman_state_dir())
        if stored:
            return stored

        return ""

    def load_key_metadata(self, dotfiles_output: str) -> None:
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

        detail_output = self.capture_or_exit(
            [self.dotdrop_cmd, "detail", "-b", *self.metadata_args, *self.all_keys]
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
        profile = self.resolved_profile
        operation_word, _ = self.operation_words(self.operation)
        prompt = f'{operation_word} all dotfiles for profile "{profile}" [Y/n] ? '
        if not sys.stdin.isatty():
            return True
        answer = self.prompt(prompt)
        if answer.lower() in {"y", "yes"}:
            return True
        if answer == "":
            return True
        print("aborted", file=sys.stderr)
        return False

    def log_profile_selection(self) -> None:
        print(f'Using dotdrop profile "{self.resolved_profile}"')

    def collect_update_changes(self) -> list[UpdateChange]:
        if not self.regular_update_keys:
            return []

        completed = self.run_update_preview(False, self.regular_update_keys)
        if completed.returncode != 0:
            return []

        return self.parse_update_changes(completed.stdout)

    @classmethod
    def parse_update_change_pairs(cls, output_text: str) -> list[tuple[str, str]]:
        overwrite_pairs: list[tuple[str, str]] = []
        for raw_line in output_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("[DRY] would update content of "):
                payload = cls.trim_trailing_whitespace(line.removeprefix("[DRY] would update content of "))
                source_file_path, separator, live_file_path = payload.partition(" from ")
                if not separator:
                    continue
                source_file_path = cls.trim_trailing_whitespace(source_file_path)
                live_file_path = cls.trim_trailing_whitespace(live_file_path)
                if cls.paths_are_identical_if_present(source_file_path, live_file_path):
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

            payload = cls.trim_trailing_whitespace(payload)
            if " " not in payload:
                continue
            live_file_path, source_file_path = payload.rsplit(" ", 1)
            live_file_path = cls.trim_trailing_whitespace(live_file_path)
            source_file_path = cls.trim_trailing_whitespace(source_file_path)
            if not source_file_path or not live_file_path:
                continue
            if cls.paths_are_identical_if_present(source_file_path, live_file_path):
                continue
            overwrite_pairs.append((source_file_path, live_file_path))

        return sorted(overwrite_pairs)

    @classmethod
    def parse_preview_transform(cls, line: str) -> PreviewTransform | None:
        command_prefix = '-> executing "'
        if not line.startswith(command_prefix) or not line.endswith('"'):
            return None

        command_text = line.removeprefix(command_prefix)[:-1]
        try:
            command_parts = shlex.split(command_text)
        except ValueError:
            return None

        script_index = -1
        for idx, part in enumerate(command_parts):
            if part.startswith("-"):
                continue
            if part.endswith(".py"):
                script_index = idx
                break
        if script_index == -1:
            return None

        input_index = script_index + 1
        output_index = script_index + 2
        if output_index >= len(command_parts):
            return None

        input_path = command_parts[input_index]
        output_path = command_parts[output_index]
        if input_path.startswith("-") or output_path.startswith("-"):
            return None

        return PreviewTransform(
            input_path=Path(input_path),
            output_path=Path(output_path),
            command=tuple(command_parts),
            output_index=output_index,
        )

    def parse_update_changes(self, output_text: str) -> list[UpdateChange]:
        overwrite_changes: list[UpdateChange] = []
        preview_transform_by_output_path: dict[str, PreviewTransform] = {}
        for raw_line in output_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            preview_transform = self.parse_preview_transform(line)
            if preview_transform is not None:
                preview_transform_by_output_path[str(preview_transform.output_path)] = preview_transform
                continue

            if line.startswith("[DRY] would update content of "):
                payload = self.trim_trailing_whitespace(line.removeprefix("[DRY] would update content of "))
                source_file_path, separator, live_file_path = payload.partition(" from ")
                if not separator:
                    continue
                source_path = Path(self.trim_trailing_whitespace(source_file_path))
                live_path = Path(self.trim_trailing_whitespace(live_file_path))
                if self.paths_are_identical_if_present(str(source_path), str(live_path)):
                    continue
                overwrite_changes.append(UpdateChange(source_path=source_path, live_path=live_path))
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

            copy_source_path_text, source_file_path = payload.rsplit(" ", 1)
            source_path = Path(self.trim_trailing_whitespace(source_file_path))
            copy_source_path = self.trim_trailing_whitespace(copy_source_path_text)
            if not copy_source_path:
                continue

            preview_transform = preview_transform_by_output_path.get(copy_source_path)
            live_path = preview_transform.input_path if preview_transform is not None else Path(copy_source_path)
            if self.paths_are_identical_if_present(str(source_path), copy_source_path):
                continue

            overwrite_changes.append(
                UpdateChange(
                    source_path=source_path,
                    live_path=live_path,
                    preview_transform=preview_transform,
                )
            )

        return sorted(overwrite_changes, key=lambda change: (str(change.source_path), str(change.live_path)))

    def build_operation_call(self, operation_targets: list[str], *, dry_run: bool = False) -> list[str]:
        dotdrop_call = [self.dotdrop_cmd, self.operation, "-b"]
        if dry_run:
            dotdrop_call.append("-d")
        dotdrop_call.extend(self.parsed.base_args)
        dotdrop_call.extend(self.metadata_args)
        if self.is_update_operation:
            dotdrop_call.extend(["-f", "-k"])
        dotdrop_call.extend(operation_targets)
        return dotdrop_call

    @staticmethod
    def build_command_with_privilege(dotdrop_call: list[str], *, run_with_sudo: bool) -> list[str]:
        if not run_with_sudo:
            return dotdrop_call

        command = ["sudo", "env", f"PATH={os.environ.get('PATH', '')}"]
        if os.environ.get("DOTDROP_CONFIG"):
            command.append(f"DOTDROP_CONFIG={os.environ['DOTDROP_CONFIG']}")
        command.extend(dotdrop_call)
        return command

    def run_update_preview(
        self,
        run_with_sudo: bool,
        operation_targets: list[str],
    ) -> subprocess.CompletedProcess[str]:
        dry_run_call = self.build_operation_call(operation_targets, dry_run=True)
        command = self.build_command_with_privilege(dry_run_call, run_with_sudo=run_with_sudo)
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

    def count_actual_update_changes(self, run_with_sudo: bool, operation_targets: list[str]) -> int | None:
        completed = self.run_update_preview(run_with_sudo, operation_targets)
        if completed.returncode != 0:
            return None
        return len(self.parse_update_changes(completed.stdout))

    def confirm_update_overwrite_targets(self) -> None:
        if not self.is_update_operation:
            return

        overwrite_changes = self.collect_update_changes()
        if not overwrite_changes:
            return

        for change in overwrite_changes:
            normalized_live_file_path = self.normalize_target_path(str(change.live_path))
            candidate_key = self.find_matching_update_key_for_path(normalized_live_file_path)

            if (
                candidate_key
                and candidate_key in self.scoped_update_key_set
                and normalized_live_file_path not in self.scoped_update_allowed_live_path_set
            ):
                self.backup_declined_update_change(change)
                continue

            if self.parsed.force_mode or not sys.stdin.isatty():
                continue

            source_path = change.source_path
            live_path = change.live_path
            if source_path.exists():
                answer = self.prompt(f'overwrite dotfiles path "{source_path}" [y/N] ? ')
            else:
                answer = self.prompt(
                    f'import live path into dotfiles "{source_path}" from "{live_path}" [y/N] ? '
                )

            if answer.lower() not in {"y", "yes"}:
                if candidate_key and self.key_is_single_file_update_target(candidate_key, normalized_live_file_path):
                    self.remove_regular_update_key(candidate_key)
                    continue
                self.backup_declined_update_change(change)

    def print_phase_header(self, header_text: str) -> None:
        if self.colors_enabled():
            print(f"\n{self.style_text('==>', '1', '34')} {self.style_text(header_text, '1')}\n")
            return
        print(f"\n==> {header_text}\n")

    @staticmethod
    def colors_enabled() -> bool:
        return sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"

    @classmethod
    def style_text(cls, text: str, *codes: str) -> str:
        if not cls.colors_enabled() or not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}{ANSI_RESET}"

    def system_phase_needs_run(self, operation_targets: list[str]) -> bool:
        if not operation_targets:
            return False

        compare_call = [self.dotdrop_cmd, "compare", "-L", "-b", *self.metadata_args]
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
            if not line or line[0].isspace():
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
    def print_phase_body_output(cls, output_text: str, *, stream: TextIO) -> None:
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
        preview_changed_count = None
        if self.is_update_operation:
            preview_changed_count = self.count_actual_update_changes(run_with_sudo, operation_targets)

        dotdrop_call = self.build_operation_call(operation_targets)
        command = self.build_command_with_privilege(dotdrop_call, run_with_sudo=run_with_sudo)

        try:
            try:
                completed = self.run_streaming_subprocess(command)
            except KeyboardInterrupt:
                emit_interrupt_notice()
                raise SystemExit(INTERRUPTED_EXIT_CODE)
        finally:
            self.cleanup_transient_transform_outputs(operation_targets)

        return PhaseExecutionResult(
            exit_code=completed.returncode,
            changed_count=(
                preview_changed_count
                if preview_changed_count is not None
                else self.parse_phase_changed_count(completed.stdout)
            ),
        )

    def cleanup_transient_transform_outputs(self, operation_targets: Iterable[str]) -> None:
        for target_key in operation_targets:
            target_src = self.source_by_key.get(target_key, "")
            if not target_src:
                continue
            transient_path = Path(f"{target_src}.trans")
            if transient_path.exists():
                self.remove_path(transient_path)

    @classmethod
    def run_streaming_subprocess(cls, command: list[str]) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        stdout_text = ""
        stderr_text = ""
        stdout_buffer = ""
        stderr_buffer = ""
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        assert process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, data="stdout")
        selector.register(process.stderr, selectors.EVENT_READ, data="stderr")

        try:
            while selector.get_map():
                for key, _ in selector.select():
                    chunk_bytes = os.read(key.fileobj.fileno(), 4096)  # type: ignore
                    if not chunk_bytes:
                        selector.unregister(key.fileobj)
                        continue
                    chunk = chunk_bytes.decode("utf-8", errors="replace")

                    if key.data == "stdout":
                        stdout_text += chunk
                        stdout_buffer = cls.write_stream_chunks(
                            stdout_buffer + chunk,
                            stream=sys.stdout,
                        )
                    else:
                        stderr_text += chunk
                        stderr_buffer = cls.write_stream_chunks(
                            stderr_buffer + chunk,
                            stream=sys.stderr,
                        )
        except KeyboardInterrupt:
            cls.terminate_process(process)
            raise
        finally:
            selector.close()

        process.wait()
        cls.flush_stream_remainder(stdout_buffer, stream=sys.stdout)
        cls.flush_stream_remainder(stderr_buffer, stream=sys.stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout_text, stderr_text)

    @classmethod
    def write_stream_chunks(cls, buffered_text: str, *, stream: TextIO) -> str:
        lines = buffered_text.splitlines(keepends=True)
        remainder = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            remainder = lines.pop()

        for line in lines:
            cls.write_output_line(line, stream=stream)
        if cls.buffer_looks_like_prompt(remainder):
            cls.flush_stream_remainder(remainder, stream=stream)
            return ""
        return remainder

    @classmethod
    def flush_stream_remainder(cls, buffered_text: str, *, stream: TextIO) -> None:
        if buffered_text:
            cls.write_output_line(buffered_text, stream=stream)

    @staticmethod
    def buffer_looks_like_prompt(buffered_text: str) -> bool:
        return buffered_text.endswith("? ")

    @staticmethod
    def write_output_line(line: str, *, stream: TextIO) -> None:
        stripped_line = line.rstrip("\r\n")
        if DOTDROP_PHASE_SUMMARY_RE.fullmatch(stripped_line):
            return
        stream.write(line)
        stream.flush()

    @staticmethod
    def terminate_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    @classmethod
    def print_phase_summary(cls, processed_count: int, updated_count: int, failed_count: int) -> None:
        if not cls.colors_enabled():
            print(f"{processed_count} file(s) processed, {updated_count} updated, {failed_count} failed")
            return

        updated_color = "32" if updated_count else "33"
        failed_color = "31" if failed_count else "32"
        processed_text = cls.style_text(f"{processed_count} file(s) processed", "1", "34")
        updated_text = cls.style_text(f"{updated_count} updated", "1", updated_color)
        failed_text = cls.style_text(f"{failed_count} failed", "1", failed_color)
        print(f"{processed_text}, {updated_text}, {failed_text}")

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

        if self.template_source_uses_dotdrop_include(Path(target_src)):
            print(
                f"skipped template-aware update: key={key_name} output={target_src} "
                "reason=dotdrop include directives are not supported"
            )
            self.last_template_update.skipped = True
            return 0, "", ""

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

    @staticmethod
    def template_source_uses_dotdrop_include(source_path: Path) -> bool:
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return DOTDROP_TEMPLATE_INCLUDE_RE.search(source_text) is not None

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

    def remove_regular_update_key(self, target_key: str) -> None:
        if target_key not in self.regular_update_key_set:
            return
        self.regular_update_keys = [key for key in self.regular_update_keys if key != target_key]
        self.regular_update_key_set.remove(target_key)

    def record_template_update_key(self, target_key: str) -> None:
        if target_key in self.template_update_key_set:
            return
        self.template_update_keys.append(target_key)
        self.template_update_key_set.add(target_key)

    def record_scoped_update_target(self, target_key: str, live_path: str) -> None:
        self.scoped_update_key_set.add(target_key)
        self.scoped_update_allowed_live_path_set.add(live_path)

    def key_is_single_file_update_target(self, target_key: str, normalized_live_path: str) -> bool:
        if normalized_live_path != self.normalized_destination_by_key.get(target_key, ""):
            return False

        source_path_text = self.source_by_key.get(target_key, "")
        if not source_path_text:
            return False

        source_path = Path(source_path_text)
        if source_path.exists():
            return source_path.is_file()
        return not source_path_text.endswith(os.sep)

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

    def backup_declined_update_change(self, change: UpdateChange) -> None:
        self.backup_declined_update_path(change.source_path)

    def backup_declined_update_path(self, source_path: Path) -> None:
        backup_dir = self.ensure_declined_update_backup_dir()
        backup_path = backup_dir / str(len(self.declined_update_backup_entries))
        original_existed = source_path.exists()
        if original_existed:
            self.copy_path_preserving_metadata(source_path, backup_path)
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


def get_dotman_state_dir() -> Path:
    xdg_state = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return Path(xdg_state) / DOTMAN_STATE_DIR_NAME


def read_default_profile(state_dir: Path) -> str:
    profile_file = state_dir / DEFAULT_PROFILE_FILENAME
    try:
        return profile_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def write_default_profile(state_dir: Path, profile_name: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / DEFAULT_PROFILE_FILENAME).write_text(profile_name + "\n", encoding="utf-8")


def unset_default_profile(state_dir: Path) -> None:
    profile_file = state_dir / DEFAULT_PROFILE_FILENAME
    try:
        profile_file.unlink()
    except FileNotFoundError:
        pass


def parse_profiles_from_config(config_path: str) -> dict[str, dict]:
    """Parse the profiles section from a dotdrop YAML config."""
    if yaml is None:
        return {}
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    # Normalize: ensure each profile value is a dict
    return {str(name): (val if isinstance(val, dict) else {}) for name, val in profiles.items()}


def compute_profile_heights(profiles: dict[str, dict]) -> dict[str, int]:
    """Compute the height of each profile in the include DAG.

    Height = longest path from a node down to any leaf (a profile with no
    includes).  A leaf has height 0.
    """
    cache: dict[str, int] = {}
    visiting: set[str] = set()

    def _height(name: str) -> int:
        if name in cache:
            return cache[name]
        if name in visiting:
            # Cycle detected — treat as leaf to avoid infinite recursion.
            return 0
        visiting.add(name)
        profile = profiles.get(name, {})
        includes = profile.get("include", [])
        if not includes:
            cache[name] = 0
        else:
            cache[name] = 1 + max(_height(child) for child in includes)
        visiting.discard(name)
        return cache[name]

    for profile_name in profiles:
        _height(profile_name)
    return cache


def rank_profiles(profiles: dict[str, dict]) -> list[str]:
    """Rank profiles: top nodes first (not included by anyone), then rest.

    Within each group, sort by height descending, then name ascending.
    """
    included_by_others: set[str] = set()
    for profile in profiles.values():
        for child in profile.get("include", []):
            included_by_others.add(child)

    heights = compute_profile_heights(profiles)
    all_names = list(profiles.keys())

    def sort_key(name: str) -> tuple[int, int, str]:
        is_top = 0 if name not in included_by_others else 1
        return (is_top, -heights.get(name, 0), name)

    all_names.sort(key=sort_key)
    return all_names


def main() -> int:
    try:
        return DotManager(sys.argv[1:]).run()
    except KeyboardInterrupt:
        emit_interrupt_notice()
        return INTERRUPTED_EXIT_CODE
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        return code


def emit_interrupt_notice() -> None:
    # Ctrl-C often leaves the cursor on the current prompt/output line.
    sys.stderr.write("\ninterrupted\n")


if __name__ == "__main__":
    raise SystemExit(main())

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
DOTDROP_COMPARE_QUOTED_KEY_RE = re.compile(r'^=> [^:]+: "([^"]+)"(?:\s|$)')
DOTDROP_COMPARE_PLAIN_KEY_RE = re.compile(r"^=> compare ([^:]+): ")
INTERRUPTED_EXIT_CODE = 130
ANSI_RESET = "\033[0m"
DEFAULT_PROFILE_FILENAME = "default-profile"
DOTMAN_STATE_DIR_NAME = "dotman"
MENU_HEADER_MARKER = "::"
MENU_HEADER_MARKER_STYLE = ("1", "34")
MENU_INDEX_STYLE = ("1", "36")
MENU_PROMPT_STYLE = ("1",)
MENU_HINT_STYLE = ("2",)
MENU_ARROW_STYLE = ("2",)
PROFILE_LABEL_STYLE = ("1", "34")
PROFILE_VALUE_STYLE = ("1", "36")
NOOP_LABEL_STYLE = ("1", "32")
NOOP_MESSAGE_STYLE = ("1",)
MENU_ACTION_STYLE_BY_NAME: dict[str, tuple[str, ...]] = {
    "install": ("1", "32"),
    "update": ("1", "36"),
    "import": ("1", "33"),
    "remove": ("1", "31"),
}


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


@dataclass(frozen=True)
class PendingSelectionItem:
    key_name: str
    action: str
    from_path: Path
    to_path: Path


@dataclass
class TemplateUpdateState:
    changed: bool = False
    skipped: bool = False


@dataclass
class PreparedTemplateUpdate:
    exit_code: int
    staged_output_path: str = ""
    helper_output_compact: str = ""
    changed: bool = False
    skipped: bool = False


@dataclass
class PhaseExecutionResult:
    exit_code: int
    changed_count: int

class FlagList:
    """Flag list that deduplicates only known repeat-safe options."""

    __slots__ = ("_args", "_index")
    BOOLEAN_OPTIONS = {
        "-b",
        "--no-banner",
        "-f",
        "--force",
        "-k",
        "--key",
        "-d",
        "-V",
        "--verbose",
        "-R",
        "--remove-existing",
        "-L",
    }
    SPLIT_VALUE_OPTIONS = {
        "-c": "--cfg",
        "--cfg": "--cfg",
        "-p": "--profile",
        "--profile": "--profile",
        "-w": "--workers",
        "--workers": "--workers",
        "-i": "--ignore",
        "--ignore": "--ignore",
        "--prompt": "--prompt",
        "--height": "--height",
        "--header": "--header",
    }

    def __init__(self) -> None:
        self._args: list[str] = []
        self._index: dict[str, int] = {}  # key -> position in _args

    def __iter__(self):
        yield from self._args

    def append(self, arg: str) -> None:
        key = self._normalize(arg)
        if key is None:
            self._args.append(arg)
            return
        if key in self._index:
            self._args[self._index[key]] = arg  # Replace in place
        else:
            self._index[key] = len(self._args)
            self._args.append(arg)

    def append_if_absent(self, arg: str) -> None:
        key = self._normalize(arg)
        if key is None:
            if arg not in self._args:
                self._args.append(arg)
            return
        if key in self._index:
            return
        self._index[key] = len(self._args)
        self._args.append(arg)

    def extend(self, args: Iterable[str]) -> None:
        for arg in self.normalize_args(args):
            self.append(arg)

    def extend_if_absent(self, args: Iterable[str]) -> None:
        for arg in self.normalize_args(args):
            self.append_if_absent(arg)

    @classmethod
    def normalize_args(cls, args: Iterable[str]) -> list[str]:
        normalized_args: list[str] = []
        pending_value_option: str | None = None
        literal_mode = False

        for arg in args:
            if pending_value_option is not None:
                normalized_args.append(f"{pending_value_option}={arg}")
                pending_value_option = None
                continue

            if literal_mode:
                normalized_args.append(arg)
                continue

            if arg == "--":
                normalized_args.append(arg)
                literal_mode = True
                continue

            canonical_option = cls.SPLIT_VALUE_OPTIONS.get(arg)
            if canonical_option is not None:
                pending_value_option = canonical_option
                continue

            normalized_args.append(arg)

        if pending_value_option is not None:
            normalized_args.append(pending_value_option)

        return normalized_args

    def _normalize(self, arg: str) -> str | None:
        """Return canonical key for safe dedup, or None when adjacency matters."""
        # Simple boolean flags (short and long forms).
        if arg in ("-b", "--no-banner"):
            return "-b"
        if arg in ("-f", "--force"):
            return "-f"
        if arg in ("-k", "--key"):
            return "-k"
        if arg == "-d":
            return "-d"
        if arg in ("-V", "--verbose"):
            return "-V"
        if arg in ("-R", "--remove-existing"):
            return "-R"
        if arg == "-L":
            return "-L"
        # Valued options that can repeat with different values.
        if arg.startswith("--ignore="):
            return None
        # Known valued options emitted as single tokens; last one wins safely.
        if arg.startswith(("--cfg=", "--workers=", "--profile=", "--prompt=", "--height=", "--header=")):
            return arg.split("=", 1)[0]
        # Unknown options may consume the following token (for example `-C PATH`).
        return None



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

        self.pending_install_compare_output: str = ""
        self.pending_install_removal_paths_by_key: dict[str, list[str]] = {}
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
        self.prepared_template_updates: dict[str, PreparedTemplateUpdate] = {}

        self.overall_exit_code = 0
        self.last_template_update = TemplateUpdateState()
        self.used_combined_operation_selection = False

    def run(self) -> int:
        if self.argv and self.argv[0] == "default":
            return self.run_default_subcommand(self.argv[1:])

        if not self.dotdrop_cmd:
            print("dotdrop not found in PATH", file=sys.stderr)
            return 127

        if not self.argv:
            return self.run_passthrough([])

        detected_operation = self.find_supported_operation(self.argv)
        is_passthrough = detected_operation is None

        if detected_operation is None:
            self.operation = ""
            self.command_args = []
            parseable_args = self.argv
        else:
            self.operation, operation_index = detected_operation
            self.command_args = self.argv[:operation_index] + self.argv[operation_index + 1 :]
            parseable_args = self.command_args

        self.parsed = self.parse_args(parseable_args)
        self.resolved_config_path = self.resolve_config_path()
        if not self.resolved_config_path:
            print(
                "unable to determine dotdrop config path; pass -c/--cfg or set DOTDROP_CONFIG",
                file=sys.stderr,
            )
            return 2

        self.repo_root = str(Path(self.resolved_config_path).parent)
        self.template_update_script = str(
            Path(self.repo_root) / "scripts" / "dotdrop_template_update.py"
        )

        self.resolved_profile = self.resolve_profile()

        if is_passthrough:
            return self.run_passthrough(self.build_passthrough_args())

        if not self.resolved_profile or (
            self.operation == "import"
            and not self.parsed.profile_was_explicitly_selected
        ):
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
            if not read_default_profile(get_dotman_state_dir()):
                print(
                    self.style_text(
                        f"tip: run 'dotman default {self.resolved_profile}' to save as default",
                        *MENU_HINT_STYLE,
                    ),
                    file=sys.stderr,
                )

        if self.operation == "import":
            flags = FlagList()
            flags.append(self.operation)
            flags.append("-b")
            flags.extend(self.metadata_args)
            flags.extend(self.parsed.base_args)
            flags.extend(self.parsed.explicit_targets)
            return self.run_passthrough(list(flags))

        dotfiles_output = self.load_dotfiles_output()
        self.load_key_metadata(dotfiles_output)
        self.select_targets()

        if not self.parsed.explicit_targets and not self.parsed.force_mode:
            self.log_profile_selection()

        if self.is_update_operation:
            try:
                self.exclude_pending_operation_items()
                if not self.has_pending_operation_targets():
                    self.print_no_pending_operation_message()
                    return self.overall_exit_code
                self.confirm_update_overwrite_targets()
                self.run_update_phases()
            finally:
                self.restore_declined_update_state()
            return self.overall_exit_code

        self.exclude_pending_operation_items()
        if not self.has_pending_operation_targets():
            self.print_no_pending_operation_message()
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

    def build_passthrough_args(self) -> list[str]:
        normalized_args = FlagList.normalize_args(self.argv)

        flags = FlagList()
        flags.extend(normalized_args)
        if self.resolved_config_path:
            flags.append_if_absent(f"--cfg={self.resolved_config_path}")
        if self.resolved_profile:
            flags.append_if_absent(f"--profile={self.resolved_profile}")
        return list(flags)

    @staticmethod
    def operation_words(operation: str) -> tuple[str, str]:
        if operation == "install":
            return "Install", "installing"
        if operation == "update":
            return "Update", "updating"
        return operation.title(), operation

    @staticmethod
    def find_supported_operation(args: list[str]) -> tuple[str, int] | None:
        pending_value_option = False

        for idx, arg in enumerate(args):
            if pending_value_option:
                pending_value_option = False
                continue

            if arg == "--":
                break

            if arg in FlagList.SPLIT_VALUE_OPTIONS:
                pending_value_option = True
                continue

            option_name, has_equals, _ = arg.partition("=")
            if has_equals and option_name in FlagList.SPLIT_VALUE_OPTIONS:
                continue

            if arg in FlagList.BOOLEAN_OPTIONS:
                continue

            if arg.startswith("-"):
                # Unknown options may belong to dotdrop itself and may consume the
                # following token. Stop here rather than guessing where the
                # operation starts.
                return None

            if arg in SUPPORTED_OPERATIONS:
                return arg, idx

            # The first positional token is the command/subcommand slot.
            return None

        return None

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
        # --opt=VALUE single tokens to keep downstream flag handling unambiguous.
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
            if candidate_path.is_file() and self._is_dotdrop_config(candidate_path):
                return str(candidate_path)

        return ""

    def _is_dotdrop_config(self, path: Path) -> bool:
        result = subprocess.run(
            [self.dotdrop_cmd, "--cfg", str(path), "validate"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def load_dotfiles_output(self) -> str:
        flags = FlagList()
        flags.append(self.dotdrop_cmd)
        flags.append("files")
        flags.append("-b")
        flags.append("-G")
        flags.extend(self.metadata_args)
        return self.capture_or_exit(
            list(flags),
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

        flags = FlagList()
        flags.append(self.dotdrop_cmd)
        flags.append("detail")
        flags.append("-b")
        flags.extend(self.metadata_args)
        flags.extend(self.all_keys)
        detail_output = self.capture_or_exit(
            list(flags),
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
        self.print_status_line(
            "profile",
            self.resolved_profile,
            label_style=PROFILE_LABEL_STYLE,
            message_style=PROFILE_VALUE_STYLE,
        )

    def has_pending_operation_targets(self) -> bool:
        if self.is_update_operation:
            return bool(self.regular_update_keys or self.template_update_keys)
        if self.is_install_operation:
            return bool(self.install_keys)
        return bool(self.parsed.explicit_targets)

    def print_no_pending_operation_message(self) -> None:
        if self.is_update_operation:
            self.print_status_line(
                "ok",
                "nothing to update",
                label_style=NOOP_LABEL_STYLE,
                message_style=NOOP_MESSAGE_STYLE,
            )
            return
        if self.is_install_operation:
            self.print_status_line(
                "ok",
                "nothing to install",
                label_style=NOOP_LABEL_STYLE,
                message_style=NOOP_MESSAGE_STYLE,
            )

    def collect_update_changes(self) -> list[UpdateChange]:
        if not self.regular_update_keys:
            return []

        completed = self.run_update_preview(False, self.regular_update_keys)
        return self.parse_update_changes_from_preview(completed)

    def exclude_pending_operation_items(self) -> None:
        if self.is_update_operation:
            self.exclude_pending_update_items()
            return
        if self.is_install_operation:
            self.exclude_pending_install_items()

    def exclude_pending_install_items(self) -> None:
        pending_keys = self.collect_pending_install_keys()
        self.install_keys = pending_keys
        if not pending_keys:
            return
        if self.parsed.force_mode or not sys.stdin.isatty():
            return

        self.used_combined_operation_selection = True
        selection_items = self._collect_install_file_selection_items(pending_keys)
        if not selection_items:
            return

        excluded_indexes = self.prompt_for_excluded_items(selection_items, operation="install")
        excluded_keys = {selection_items[i - 1].key_name for i in excluded_indexes}
        self.install_keys = [k for k in pending_keys if k not in excluded_keys]

    def _collect_install_file_selection_items(self, pending_keys: list[str]) -> list[PendingSelectionItem]:
        items_by_key: dict[str, list[PendingSelectionItem]] = {}
        for raw_line in self.pending_install_compare_output.splitlines():
            if not raw_line or raw_line[0].isspace():
                continue
            quoted_match = DOTDROP_COMPARE_QUOTED_KEY_RE.match(raw_line.strip())
            if not quoted_match:
                continue
            dest_path_str = quoted_match.group(1)
            key_name = self.find_matching_install_key_for_path(dest_path_str, pending_keys)
            if not key_name:
                continue
            source_path_str = self._derive_install_source_path(key_name, dest_path_str)
            items_by_key.setdefault(key_name, []).append(PendingSelectionItem(
                key_name=key_name,
                action="install",
                from_path=Path(source_path_str),
                to_path=Path(dest_path_str),
            ))

        result: list[PendingSelectionItem] = []
        for key_name in pending_keys:
            file_items = items_by_key.get(key_name, [])
            removal_paths = self.pending_install_removal_paths_by_key.get(key_name, [])
            removal_items = [
                PendingSelectionItem(
                    key_name=key_name,
                    action="remove",
                    from_path=Path(p),
                    to_path=Path(p),
                )
                for p in removal_paths
            ]
            if file_items or removal_items:
                result.extend(file_items)
                result.extend(removal_items)
            else:
                result.append(PendingSelectionItem(
                    key_name=key_name,
                    action="install",
                    from_path=Path(self.source_by_key[key_name]),
                    to_path=Path(self.destination_by_key[key_name]),
                ))
        return result

    def _derive_install_source_path(self, key_name: str, dest_path_str: str) -> str:
        key_dest = self.normalized_destination_by_key.get(key_name, "")
        key_src = self.source_by_key.get(key_name, "")
        norm_dest = self.normalize_target_path(dest_path_str)
        if key_dest and key_src and norm_dest.startswith(key_dest):
            relative = norm_dest[len(key_dest):]
            return key_src.rstrip(os.sep) + relative
        return dest_path_str

    def exclude_pending_update_items(self) -> None:
        regular_candidates = self.collect_pending_regular_update_candidates()
        template_candidate_keys = self.collect_pending_template_update_keys()
        self.regular_update_keys = [key_name for key_name, _change in regular_candidates]
        self.regular_update_key_set = set(self.regular_update_keys)
        self.template_update_keys = list(template_candidate_keys)
        self.template_update_key_set = set(self.template_update_keys)

        if self.parsed.force_mode or not sys.stdin.isatty():
            return

        selection_items = [
            PendingSelectionItem(
                key_name=key_name,
                action=self.pending_update_action_name(change),
                from_path=change.live_path,
                to_path=change.source_path,
            )
            for key_name, change in regular_candidates
        ]
        selection_items.extend(
            PendingSelectionItem(
                key_name=key_name,
                action="template",
                from_path=Path(self.destination_by_key[key_name]),
                to_path=Path(self.source_by_key[key_name]),
            )
            for key_name in template_candidate_keys
        )

        if not selection_items:
            return

        self.used_combined_operation_selection = True
        excluded_indexes = self.prompt_for_excluded_items(selection_items, operation="update")
        included_regular_keys = {
            key_name
            for index, (key_name, _change) in enumerate(regular_candidates, start=1)
            if index not in excluded_indexes
        }

        for key_name in list(self.regular_update_keys):
            if key_name not in included_regular_keys:
                self.remove_regular_update_key(key_name)

        for index, (key_name, change) in enumerate(regular_candidates, start=1):
            if index in excluded_indexes and key_name in included_regular_keys:
                self.backup_declined_update_change(change)

        template_index_offset = len(regular_candidates)
        for offset, key_name in enumerate(template_candidate_keys, start=1):
            if template_index_offset + offset in excluded_indexes:
                self.remove_template_update_key(key_name)

    def collect_pending_install_keys(self) -> list[str]:
        if not self.install_keys:
            return []

        compare_completed = self.run_install_compare(self.install_keys)
        if compare_completed.returncode not in {0, 1}:
            return list(self.install_keys)

        compare_output = compare_completed.stdout + compare_completed.stderr
        pending_keys, compare_was_uncertain = self.parse_compare_pending_keys(
            compare_output,
            self.install_keys,
        )
        if compare_was_uncertain:
            return list(self.install_keys)

        if self.parsed.remove_existing_mode:
            removal_keys = self.collect_remove_existing_pending_install_keys(self.install_keys)
            pending_keys.update(removal_keys)

        result = [key_name for key_name in self.install_keys if key_name in pending_keys]
        if result:
            self.pending_install_compare_output = compare_output
        return result

    def collect_pending_regular_update_candidates(self) -> list[tuple[str, UpdateChange]]:
        pending_candidates: list[tuple[str, UpdateChange]] = []
        for change in self.collect_update_changes():
            normalized_live_file_path = self.normalize_target_path(str(change.live_path))
            candidate_key = self.find_matching_update_key_for_path(normalized_live_file_path)

            if (
                candidate_key
                and candidate_key in self.scoped_update_key_set
                and normalized_live_file_path not in self.scoped_update_allowed_live_path_set
            ):
                self.backup_declined_update_change(change)
                continue

            pending_candidates.append((candidate_key, change))

        return pending_candidates

    def collect_pending_template_update_keys(self) -> list[str]:
        pending_keys: list[str] = []
        for key_name in self.template_update_keys:
            prepare_exit_code, staged_output_path, helper_output_compact = self.prepare_template_update_for_key(
                key_name,
                report_skip_reason=False,
            )
            prepared_update = PreparedTemplateUpdate(
                exit_code=prepare_exit_code,
                staged_output_path=staged_output_path,
                helper_output_compact=helper_output_compact,
                changed=self.last_template_update.changed,
                skipped=self.last_template_update.skipped,
            )
            self.prepared_template_updates[key_name] = prepared_update
            if prepare_exit_code != 0:
                if self.overall_exit_code == 0:
                    self.overall_exit_code = prepare_exit_code
                continue
            if prepared_update.changed:
                pending_keys.append(key_name)
        return pending_keys

    @staticmethod
    def pending_update_action_name(change: UpdateChange) -> str:
        if change.source_path.exists():
            return "update"
        return "import"

    @classmethod
    def prompt_for_excluded_items(
        cls,
        selection_items: list[PendingSelectionItem],
        *,
        operation: str,
    ) -> set[int]:
        cls.print_pending_selection_header(operation)
        for index, item in enumerate(selection_items, start=1):
            cls.print_pending_selection_item(index, item)

        while True:
            answer = cls.prompt(cls.pending_selection_prompt())
            try:
                return cls.parse_selection_indexes(answer, len(selection_items))
            except ValueError as exc:
                print(f"invalid selection: {exc}", file=sys.stderr)

    @classmethod
    def print_pending_selection_header(cls, operation: str) -> None:
        header_text = f"Select items to exclude from {operation}:"
        if not cls.colors_enabled():
            print(header_text)
            return
        print(
            f"{cls.style_text(MENU_HEADER_MARKER, *MENU_HEADER_MARKER_STYLE)} "
            f"{cls.style_text(header_text, '1')}"
        )

    @classmethod
    def print_pending_selection_item(cls, index: int, item: PendingSelectionItem) -> None:
        item_text = f"[{item.action}] {item.key_name}: {item.from_path} -> {item.to_path}"
        if not cls.colors_enabled():
            print(f"  {index:>2}) {item_text}")
            return

        item_style = MENU_ACTION_STYLE_BY_NAME.get(item.action, ("1",))
        action_text = cls.style_text(f"[{item.action}]", *item_style)
        key_text = cls.style_text(item.key_name, "1")
        arrow_text = cls.style_text("->", *MENU_ARROW_STYLE)
        print(
            f"  {cls.style_text(f'{index:>2})', *MENU_INDEX_STYLE)} "
            f"{action_text} {key_text}: {item.from_path} {arrow_text} {item.to_path}"
        )

    @classmethod
    def pending_selection_prompt(cls) -> str:
        prompt_text = 'Exclude by number or range'
        hint_text = '(default: none; e.g. "1 2 4-6" or "^3")'
        if not cls.colors_enabled():
            return f"{prompt_text} {hint_text}: "
        return (
            f"{cls.style_text(MENU_HEADER_MARKER, *MENU_HEADER_MARKER_STYLE)} "
            f"{cls.style_text(prompt_text, *MENU_PROMPT_STYLE)} "
            f"{cls.style_text(hint_text, *MENU_HINT_STYLE)}: "
        )

    @staticmethod
    def parse_selection_token(token: str, item_count: int) -> set[int]:
        if token.isdigit():
            index = int(token)
            if not 1 <= index <= item_count:
                raise ValueError(f"selection index out of range: {index}")
            return {index}

        if "-" not in token:
            raise ValueError(f"unsupported token: {token}")

        start_text, end_text = token.split("-", 1)
        if not start_text.isdigit() or not end_text.isdigit():
            raise ValueError(f"unsupported token: {token}")

        start_index = int(start_text)
        end_index = int(end_text)
        if start_index > end_index:
            raise ValueError(f"invalid range: {token}")
        if start_index < 1 or end_index > item_count:
            raise ValueError(f"selection index out of range: {token}")
        return set(range(start_index, end_index + 1))

    @classmethod
    def parse_selection_indexes(cls, raw_answer: str, item_count: int) -> set[int]:
        answer = raw_answer.strip()
        if not answer:
            return set()

        keep_only_mode = answer.startswith("^")
        if keep_only_mode:
            answer = answer[1:].strip()
            if not answer:
                raise ValueError("missing keep-only selection after '^'")

        selected_indexes: set[int] = set()
        for token in re.split(r"[\s,]+", answer):
            if not token:
                continue
            selected_indexes.update(cls.parse_selection_token(token, item_count))

        if keep_only_mode:
            return set(range(1, item_count + 1)) - selected_indexes
        return selected_indexes

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

    def build_operation_call(
        self,
        operation_targets: list[str],
        *,
        dry_run: bool = False,
        operation: str | None = None,
    ) -> list[str]:
        op = operation if operation is not None else self.operation
        flags = FlagList()
        flags.append(self.dotdrop_cmd)
        flags.append(op)
        flags.append("-b")
        if dry_run:
            flags.append("-d")
        flags.extend(self.parsed.base_args)
        flags.extend(self.metadata_args)
        if op == "install" and self.used_combined_operation_selection:
            flags.append("-f")
        if op == "update":  # Use op param, not self.is_update_operation
            flags.extend(["-f", "-k"])
        flags.extend(operation_targets)
        return list(flags)

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
        changes = self.parse_update_changes_from_preview(completed)
        if changes:
            return len(changes)
        if completed.returncode != 0:
            return None
        return 0

    def parse_update_changes_from_preview(
        self,
        completed: subprocess.CompletedProcess[str],
    ) -> list[UpdateChange]:
        preview_output = completed.stdout
        if completed.stderr:
            preview_output = f"{preview_output}\n{completed.stderr}" if preview_output else completed.stderr
        changes = self.parse_update_changes(preview_output)
        if changes:
            return changes
        if completed.returncode != 0:
            return []
        return self.parse_update_changes(completed.stdout)

    def confirm_update_overwrite_targets(self) -> None:
        if not self.is_update_operation or self.parsed.force_mode or not sys.stdin.isatty():
            return

    def print_phase_header(self, header_text: str) -> None:
        if self.colors_enabled():
            print(f"\n{self.style_text('==>', '1', '34')} {self.style_text(header_text, '1')}\n")
            return
        print(f"\n==> {header_text}\n")

    @classmethod
    def print_status_line(
        cls,
        label: str,
        message: str,
        *,
        label_style: tuple[str, ...] = ("1",),
        message_style: tuple[str, ...] = (),
    ) -> None:
        if not cls.colors_enabled():
            print(f"{label}: {message}")
            return

        styled_label = cls.style_text(f"{label}:", *label_style)
        styled_message = cls.style_text(message, *message_style) if message_style else message
        print(f"{styled_label} {styled_message}")

    @staticmethod
    def colors_enabled() -> bool:
        return sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"

    @classmethod
    def style_text(cls, text: str, *codes: str) -> str:
        if not cls.colors_enabled() or not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}{ANSI_RESET}"

    def run_install_compare(self, operation_targets: list[str]) -> subprocess.CompletedProcess[str]:
        # use compare instead of dry-run bc dry-run always assume changes
        flags = FlagList()
        flags.append(self.dotdrop_cmd)
        flags.append("compare")
        flags.append("-L")
        flags.append("-b")
        flags.extend(self.metadata_args)
        for focus_target in operation_targets:
            compare_path = self.normalized_destination_by_key.get(
                focus_target, focus_target
            )
            flags.extend(["-C", compare_path])
        return subprocess.run(
            list(flags),
            check=False,
            capture_output=True,
            text=True,
        )

    def parse_compare_pending_keys(
        self,
        output_text: str,
        operation_targets: list[str],
    ) -> tuple[set[str], bool]:
        target_key_set = set(operation_targets)
        pending_keys: set[str] = set()
        for raw_line in output_text.splitlines():
            if not raw_line or raw_line[0].isspace():
                continue

            line = raw_line.strip()
            if line.endswith(" dotfile(s) compared."):
                continue

            quoted_match = DOTDROP_COMPARE_QUOTED_KEY_RE.match(line)
            if quoted_match:
                matched_key = self.resolve_compare_pending_key(
                    quoted_match.group(1),
                    operation_targets,
                )
                if matched_key in target_key_set:
                    pending_keys.add(matched_key)
                    continue
                return set(target_key_set), True

            plain_match = DOTDROP_COMPARE_PLAIN_KEY_RE.match(line)
            if plain_match:
                matched_key = self.resolve_compare_pending_key(
                    plain_match.group(1),
                    operation_targets,
                )
                if matched_key in target_key_set:
                    pending_keys.add(matched_key)
                    continue
                return set(target_key_set), True

            return set(target_key_set), True

        return pending_keys, False

    def resolve_compare_pending_key(self, candidate: str, operation_targets: list[str]) -> str:
        if candidate in operation_targets:
            return candidate
        return self.find_matching_install_key_for_path(candidate, operation_targets)

    def collect_remove_existing_pending_install_keys(self, operation_targets: list[str]) -> set[str]:
        dry_run_call = self.build_operation_call(
            operation_targets, dry_run=True, operation="install"
        )
        dry_run_completed = subprocess.run(
            dry_run_call,
            check=False,
            capture_output=True,
            text=True,
        )
        if dry_run_completed.returncode != 0:
            return set(operation_targets)

        dry_run_output = dry_run_completed.stdout + dry_run_completed.stderr
        pending_keys: set[str] = set()
        removal_paths_by_key: dict[str, list[str]] = {}
        for line in dry_run_output.splitlines():
            if line.startswith("[DRY] would remove "):
                removed_path_text = self.trim_trailing_whitespace(line.removeprefix("[DRY] would remove "))
                matched_key = self.find_matching_install_key_for_path(removed_path_text, operation_targets)
                if matched_key:
                    pending_keys.add(matched_key)
                    removal_paths_by_key.setdefault(matched_key, []).append(removed_path_text)
                    continue
                return set(operation_targets)
        self.pending_install_removal_paths_by_key = removal_paths_by_key
        return pending_keys

    def find_matching_install_key_for_path(self, candidate_path: str, operation_targets: list[str]) -> str:
        normalized_candidate_path = self.normalize_target_path(candidate_path)
        matched_key = ""
        matched_length = 0
        for key_name in operation_targets:
            known_destination = self.normalized_destination_by_key.get(key_name, "")
            if not known_destination:
                continue
            if normalized_candidate_path == known_destination:
                return key_name
            if (
                normalized_candidate_path.startswith(known_destination + os.sep)
                and len(known_destination) > matched_length
            ):
                matched_key = key_name
                matched_length = len(known_destination)
        return matched_key

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
        phase_result = self.run_phase_operation(phase_name, run_with_sudo, phase_targets)
        failed_count = 1 if phase_result.exit_code != 0 else 0
        self.print_phase_summary(len(phase_targets), phase_result.changed_count, failed_count)

    def prepare_template_update_for_key(
        self, key_name: str, *, report_skip_reason: bool = True
    ) -> tuple[int, str, str]:
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
            if report_skip_reason:
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
        if self.used_combined_operation_selection:
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
        prepared_update = self.prepared_template_updates.pop(key_name, None)
        if prepared_update is None:
            prepare_exit_code, staged_output_path, helper_output_compact = self.prepare_template_update_for_key(
                key_name
            )
        else:
            self.last_template_update = TemplateUpdateState(
                changed=prepared_update.changed,
                skipped=prepared_update.skipped,
            )
            prepare_exit_code = prepared_update.exit_code
            staged_output_path = prepared_update.staged_output_path
            helper_output_compact = prepared_update.helper_output_compact

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

    def remove_template_update_key(self, target_key: str) -> None:
        if target_key not in self.template_update_key_set:
            return
        self.template_update_keys = [key for key in self.template_update_keys if key != target_key]
        self.template_update_key_set.remove(target_key)
        self.prepared_template_updates.pop(target_key, None)

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
        self.prepared_template_updates = {}
        self.used_combined_operation_selection = False

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

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "packages/bin/files/bin/sudo-request-context"
ASKPASS_GUI = REPO_ROOT / "packages/bin/files/bin/askpass-gui"
STOCK_PROMPT = "[sudo] password for xian: "


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def run_as_child_of_sudo(prompt: str, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Render context while the parent process carries the sudo-style argv.

    The helper reads the invocation from its parent, so that parent has to be a
    real process. python3 is exec'd with argv[0]="sudo" and reads its program
    from stdin ("-"), which puts the fake invocation in front of the
    interpreter's own arguments.
    """
    code = (
        "import subprocess\n"
        f"raise SystemExit(subprocess.run([{str(HELPER)!r}, {prompt!r}]).returncode)\n"
    )
    return subprocess.run(
        ["sudo", "-", *argv],
        executable=sys.executable,
        input=code.encode(),
        capture_output=True,
    )


def run_sourced(script: str) -> str:
    """Run helper functions directly, with caller-supplied stubs."""
    completed = subprocess.run(
        ["bash", "-c", f"set -f\n. {shlex.quote(str(HELPER))}\n{script}"],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def row(output: str, label: str) -> str | None:
    for line in output.splitlines():
        if line.startswith(label):
            return line[len(label):].strip()
    return None


def test_reports_requester_command_reason_and_directory() -> None:
    prompt = "Reason: install build dependency\nPassword for %p: "
    argv = ["-A", "-p", prompt, "/usr/bin/apt", "install", "-y", "shellcheck"]

    completed = run_as_child_of_sudo(prompt, argv)

    assert completed.returncode == 0, completed.stderr.decode()
    output = completed.stdout.decode()
    requester = row(output, "Requester")
    assert requester is not None, output
    assert "sudo(" in requester
    assert "no tty" in requester
    assert row(output, "Command") == "/usr/bin/apt install -y shellcheck"
    assert row(output, "Directory")
    assert row(output, "Reason") == "install build dependency"
    assert output.rstrip().endswith("Password for %p:")


def test_hides_the_reason_row_when_the_caller_supplied_none() -> None:
    completed = run_as_child_of_sudo(STOCK_PROMPT, ["-A", "/usr/bin/true"])

    output = completed.stdout.decode()
    assert row(output, "Requester") is not None
    assert row(output, "Reason") is None
    assert output.rstrip().endswith("[sudo] password for xian:")


def test_command_skips_flags_and_their_values() -> None:
    argv = ["-A", "-u", "root", "--chdir=/tmp", "-E", "--", "/usr/bin/ls", "-la"]

    completed = run_as_child_of_sudo(STOCK_PROMPT, argv)

    assert row(completed.stdout.decode(), "Command") == "/usr/bin/ls -la"


def test_command_row_is_capped_to_the_dialog_budget() -> None:
    script = "echo " + "x" * 400

    completed = run_as_child_of_sudo(STOCK_PROMPT, ["-A", "/bin/sh", "-c", script])

    command = row(completed.stdout.decode(), "Command")
    assert command is not None
    assert len(command) <= 120, command
    assert command.endswith("…")


def test_flattened_ps_output_finds_the_command_after_the_prompt() -> None:
    flattened = (
        "sudo -A -p Agent needs elevated privileges. Reason: install build dependency"
        " Password for %p: /usr/bin/apt install -y shellcheck"
    )

    assert (
        run_sourced(f"parse_invocation flattened {flattened}").strip()
        == "/usr/bin/apt install -y shellcheck"
    )


def test_flattened_ps_output_without_a_prompt_colon_keeps_the_command() -> None:
    flattened = "sudo -A -p Password /usr/bin/true"

    assert run_sourced(f"parse_invocation flattened {flattened}").strip() == "/usr/bin/true"


def test_reparented_caller_falls_back_to_the_cgroup_scope() -> None:
    stubs = textwrap.dedent(
        """
        parent_pid() { case $1 in 4242) printf '933' ;; 933) printf '1' ;; *) printf '' ;; esac; }
        process_name() { case $1 in 4242) printf 'sudo' ;; 933) printf 'systemd' ;; esac; }
        tty_label() { printf 'no tty'; }
        cgroup_scope() { printf 'app-ghostty-surface-8712'; }
        render_requester 4242
        """
    )

    output = run_sourced(stubs)

    assert "sudo(4242) ← systemd(933)" in output
    assert "app-ghostty-surface-8712" in output


def test_askpass_gui_renders_context_in_an_entry_dialog(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    zenity_log = tmp_path / "zenity-args.log"
    write_executable(
        fake_bin / "zenity",
        f"""#!/bin/sh
printf '%s\n' "$*" >{shlex.quote(str(zenity_log))}
printf '%s\n' 'hunter2'
""",
    )

    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    completed = subprocess.run(
        [str(ASKPASS_GUI), "Reason: because the tests need it\nPassword for %p: "],
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "hunter2\n"
    arguments = zenity_log.read_text(encoding="utf-8")
    # --password ignores --text entirely, so this flag set is the regression
    # guard for a dialog that never showed the reason.
    assert "--entry --hide-text" in arguments
    assert "--no-markup" in arguments
    assert "Reason" in arguments
    assert "because the tests need it" in arguments

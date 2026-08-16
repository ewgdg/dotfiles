from __future__ import annotations

import os
from pathlib import Path
import pty
import re
import select
import shlex
import signal
import subprocess
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_ZSH = REPO_ROOT / "packages/shell/files/config/zsh/agents.zsh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def keyring_entry_path(keyring_state: Path, service: str) -> Path:
    description = f"api-key-cache-v1:{service}"
    cache_id = re.sub(r"[^A-Za-z0-9._-]", "_", description)
    return keyring_state / cache_id


def prepare_fake_commands(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    runtime_dir = tmp_path / "runtime"
    bin_dir.mkdir()
    runtime_dir.mkdir(mode=0o700)

    keyring_state = tmp_path / "keyring-state"
    keyring_state.mkdir()
    keyctl_log = tmp_path / "keyctl.log"
    op_count = tmp_path / "op-count"

    write_executable(
        bin_dir / "keyctl",
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$TEST_KEYCTL_LOG"
cache_id() {
  printf '%s' "$1" | tr -c '[:alnum:]._-' '_'
}
case "$1" in
  search)
    id=$(cache_id "$4")
    test -f "$TEST_KEYCTL_STATE/$id" || exit 1
    printf '%s\n' "$id"
    ;;
  pipe)
    cat "$TEST_KEYCTL_STATE/$2"
    ;;
  padd)
    id=$(cache_id "$3")
    temporary_state="$TEST_KEYCTL_STATE/${id}.$$"
    cat > "$temporary_state"
    mv "$temporary_state" "$TEST_KEYCTL_STATE/$id"
    printf '%s\n' "$id"
    ;;
  timeout)
    printf '%s\n' "$2 $3" >> "$TEST_KEYCTL_TIMEOUT"
    ;;
  unlink)
    if test -f "$TEST_KEYCTL_STATE/$2"; then
      unlink "$TEST_KEYCTL_STATE/$2"
    fi
    ;;
  *)
    printf 'unexpected keyctl command: %s\n' "$*" >&2
    exit 2
    ;;
esac
""",
    )
    write_executable(
        bin_dir / "op",
        """#!/bin/sh
set -eu
exec 9>>"$TEST_OP_LOCK"
flock -x 9
count=0
if test -f "$TEST_OP_COUNT"; then
  count=$(cat "$TEST_OP_COUNT")
fi
count=$((count + 1))
printf '%s\n' "$count" > "$TEST_OP_COUNT"
flock -u 9
if test -n "${TEST_OP_DESCENDANT_DELAY:-}"; then
  sleep "$TEST_OP_DESCENDANT_DELAY" </dev/null >/dev/null 2>&1 &
  printf '%s\n' "$!" >> "$TEST_OP_DESCENDANT_PIDS"
fi
sleep "${TEST_OP_DELAY:-0}"
index=1
while :; do
  eval "reference=\\${OP_CACHE_KEY_${index}:-}"
  test -n "$reference" || break
  service=${reference#op://dev/}
  service=${service%/credential}
  printf 'value-%s\n' "$service"
  index=$((index + 1))
done
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "TEST_KEYCTL_LOG": str(keyctl_log),
            "TEST_KEYCTL_STATE": str(keyring_state),
            "TEST_KEYCTL_TIMEOUT": str(tmp_path / "keyctl-timeout"),
            "TEST_OP_COUNT": str(op_count),
            "TEST_OP_LOCK": str(tmp_path / "op-count.lock"),
        }
    )
    return environment, keyring_state, keyctl_log, op_count


def load_script(*, prelude: str = "", epilogue: str = "") -> str:
    return f"""
_ensure_command() {{ command -v "$1" >/dev/null 2>&1 }}
source {shlex.quote(str(AGENTS_ZSH))}
{prelude}
typeset -a reply
_load_api_keys alpha-api beta-api || exit 1
print -r -- "${{(j:,:)reply}}"
{epilogue}
"""


def run_zsh(
    script: str, environment: dict[str, str], *, timeout: float = 5
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["zsh", "-fc", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def read_until(file_descriptor: int, expected: bytes, timeout: float = 3) -> bytes:
    deadline = time.monotonic() + timeout
    output = b""
    while expected not in output and time.monotonic() < deadline:
        readable, _, _ = select.select([file_descriptor], [], [], 0.05)
        if readable:
            output += os.read(file_descriptor, 4096)

    assert expected in output, output.decode(errors="replace")
    return output


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=0.5)


def close_interactive_shell(shell_pid: int, terminal: int) -> None:
    try:
        os.write(terminal, b"exit\n")
    except OSError:
        pass

    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        waited_pid, _ = os.waitpid(shell_pid, os.WNOHANG)
        if waited_pid == shell_pid:
            break
        time.sleep(0.01)
    else:
        try:
            os.killpg(shell_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(shell_pid, 0)

    os.close(terminal)


def test_linux_reuses_per_service_keyring_entries_across_loads(tmp_path: Path) -> None:
    environment, keyring_state, _, op_count = prepare_fake_commands(tmp_path)

    completed = run_zsh(
        load_script(
            epilogue='\n_load_api_keys alpha-api beta-api || exit 1\nprint -r -- "${(j:,:)reply}"'
        ),
        environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "alpha-api,value-alpha-api,beta-api,value-beta-api",
        "alpha-api,value-alpha-api,beta-api,value-beta-api",
    ]
    assert op_count.read_text(encoding="utf-8").strip() == "1"
    assert sorted(path.name for path in keyring_state.iterdir()) == [
        "api-key-cache-v1_alpha-api",
        "api-key-cache-v1_beta-api",
    ]
    assert {
        line.rsplit(" ", 1)[1]
        for line in (tmp_path / "keyctl-timeout").read_text(encoding="utf-8").splitlines()
    } == {"43200"}


def test_linux_cache_serializes_concurrent_misses(tmp_path: Path) -> None:
    environment, _, _, op_count = prepare_fake_commands(tmp_path)
    environment["TEST_OP_DELAY"] = "0.25"
    script = load_script()

    processes = [
        subprocess.Popen(
            ["zsh", "-fc", script],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=10) for process in processes]

    assert [process.returncode for process in processes] == [0, 0], results
    assert [stdout.strip() for stdout, _ in results] == [
        "alpha-api,value-alpha-api,beta-api,value-beta-api",
        "alpha-api,value-alpha-api,beta-api,value-beta-api",
    ]
    assert op_count.read_text(encoding="utf-8").strip() == "1"


def test_refresh_does_not_leave_the_lock_with_external_descendants(tmp_path: Path) -> None:
    environment, _, _, op_count = prepare_fake_commands(tmp_path)
    descendant_pids = tmp_path / "op-descendant-pids"
    environment.update(
        {
            "TEST_OP_DESCENDANT_DELAY": "30",
            "TEST_OP_DESCENDANT_PIDS": str(descendant_pids),
        }
    )
    script = "\n".join(
        [
            '_ensure_command() { command -v "$1" >/dev/null 2>&1 }',
            f"source {shlex.quote(str(AGENTS_ZSH))}",
            "api-key-cache-refresh alpha-api || exit 1",
            "api-key-cache-refresh alpha-api || exit 1",
        ]
    )

    try:
        completed = subprocess.run(
            ["zsh", "-fc", script],
            env=environment,
            capture_output=True,
            text=True,
            timeout=2,
        )
    finally:
        if descendant_pids.exists():
            for pid in descendant_pids.read_text(encoding="utf-8").splitlines():
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "API key cache: refreshed",
        "API key cache: refreshed",
    ]
    assert op_count.read_text(encoding="utf-8").strip() == "2"


def test_interrupted_refresh_releases_the_lock(tmp_path: Path) -> None:
    environment, _, _, op_count = prepare_fake_commands(tmp_path)
    environment.update(
        {"PS1": "INITIAL> ", "TERM": "dumb", "TEST_OP_DELAY": "30"}
    )
    shell_pid, terminal = pty.fork()

    if shell_pid == 0:
        os.execvpe("zsh", ["zsh", "-df"], environment)

    try:
        read_until(terminal, b"INITIAL> ")
        os.write(terminal, b"stty -echo\n")
        read_until(terminal, b"INITIAL> ")
        setup = "; ".join(
            [
                "PS1='READY> '",
                '_ensure_command() { command -v "$1" >/dev/null 2>&1 }',
                f"source {shlex.quote(str(AGENTS_ZSH))}",
                "print -r -- SETUP_DONE",
            ]
        )
        os.write(terminal, f"{setup}\n".encode())
        read_until(terminal, b"READY> ")
        os.write(terminal, b"api-key-cache-refresh alpha-api\n")

        deadline = time.monotonic() + 3
        while not op_count.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert op_count.exists(), "refresh did not reach the 1Password resolver"

        os.write(terminal, b"\x03")
        read_until(terminal, b"READY> ")

        retry_environment = environment.copy()
        retry_environment.update(
            {
                "API_KEY_CACHE_LOCK_TIMEOUT_SECONDS": "1",
                "TEST_OP_DELAY": "0",
            }
        )
        completed = run_zsh(
            "\n".join(
                [
                    '_ensure_command() { command -v "$1" >/dev/null 2>&1 }',
                    f"source {shlex.quote(str(AGENTS_ZSH))}",
                    "api-key-cache-refresh alpha-api",
                ]
            ),
            retry_environment,
            timeout=0.5,
        )

        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == "API key cache: refreshed"
    finally:
        close_interactive_shell(shell_pid, terminal)


def test_cache_commands_stop_waiting_when_the_lock_limit_is_reached(tmp_path: Path) -> None:
    environment, _, _, op_count = prepare_fake_commands(tmp_path)
    lock_path = Path(environment["XDG_RUNTIME_DIR"]) / "api-key-cache.lock"
    lock_path.touch()
    holder = subprocess.Popen(
        [
            "zsh",
            "-fc",
            "zmodload zsh/system; zsystem flock -f lock_fd \"$1\"; "
            'print -r -- acquired; sleep 30',
            "zsh",
            str(lock_path),
        ],
        env=environment,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    try:
        assert holder.stdout is not None
        read_until(holder.stdout.fileno(), b"acquired\n", timeout=1)
        environment["API_KEY_CACHE_LOCK_TIMEOUT_SECONDS"] = "0.1"
        completed = run_zsh(
            "\n".join(
                [
                    '_ensure_command() { command -v "$1" >/dev/null 2>&1 }',
                    f"source {shlex.quote(str(AGENTS_ZSH))}",
                    "api-key-cache-refresh alpha-api",
                ]
            ),
            environment,
            timeout=0.5,
        )
        clear_completed = run_zsh(
            "\n".join(
                [
                    '_ensure_command() { command -v "$1" >/dev/null 2>&1 }',
                    f"source {shlex.quote(str(AGENTS_ZSH))}",
                    "api-key-cache-clear alpha-api",
                ]
            ),
            environment,
            timeout=0.5,
        )
    finally:
        terminate_process_group(holder)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "API key cache: refreshed"
    assert "Unable to lock the Linux API key cache; bypassing cache" in completed.stderr
    assert clear_completed.returncode == 1
    assert clear_completed.stdout == ""
    assert "Unable to lock the Linux API key cache" in clear_completed.stderr
    assert op_count.read_text(encoding="utf-8").strip() == "1"


def test_refresh_bypasses_a_lock_file_that_cannot_be_opened(tmp_path: Path) -> None:
    environment, _, _, op_count = prepare_fake_commands(tmp_path)
    lock_path = Path(environment["XDG_RUNTIME_DIR"]) / "api-key-cache.lock"
    lock_path.mkdir()

    completed = run_zsh(
        "\n".join(
            [
                '_ensure_command() { command -v "$1" >/dev/null 2>&1 }',
                f"source {shlex.quote(str(AGENTS_ZSH))}",
                "api-key-cache-refresh alpha-api",
            ]
        ),
        environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "API key cache: refreshed"
    assert "Unable to open the Linux API key cache lock; bypassing cache" in completed.stderr
    assert op_count.read_text(encoding="utf-8").strip() == "1"


def test_non_linux_uses_current_one_password_path_without_cache(tmp_path: Path) -> None:
    environment, keyring_state, keyctl_log, op_count = prepare_fake_commands(tmp_path)

    completed = run_zsh(
        load_script(
            prelude="OSTYPE=darwin",
            epilogue="\n_load_api_keys alpha-api beta-api || exit 1",
        ),
        environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert op_count.read_text(encoding="utf-8").strip() == "2"
    assert not any(keyring_state.iterdir())
    assert not keyctl_log.exists()


def test_corrupt_linux_cache_is_replaced_under_lock(tmp_path: Path) -> None:
    environment, keyring_state, _, op_count = prepare_fake_commands(tmp_path)
    corrupt_entry = keyring_entry_path(keyring_state, "alpha-api")
    corrupt_entry.write_text("not-a-valid-cache", encoding="utf-8")

    completed = run_zsh(load_script(), environment)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "alpha-api,value-alpha-api,beta-api,value-beta-api"
    assert op_count.read_text(encoding="utf-8").strip() == "1"
    assert "not-a-valid-cache" not in corrupt_entry.read_text(encoding="utf-8")
    assert keyring_entry_path(keyring_state, "beta-api").exists()


def test_pi_owns_its_service_list_locally() -> None:
    source = AGENTS_ZSH.read_text(encoding="utf-8")
    service_list = re.search(
        r"local -a api_key_services=\(\n(?P<services>.*?)\n  \)",
        source,
        re.DOTALL,
    )

    assert "_AGENT_API_KEY_SERVICES" not in source
    assert service_list is not None
    assert service_list.group("services").split() == [
        "deepseek-api",
        "brave-api",
        "exa-api",
    ]


def test_cache_ttl_has_one_config_variable() -> None:
    source = AGENTS_ZSH.read_text(encoding="utf-8")

    assert "_API_KEY_CACHE_DEFAULT_TTL_SECONDS" not in source
    assert "typeset -g API_KEY_CACHE_TTL_SECONDS=" in source


def test_cache_internals_use_a_platform_neutral_namespace() -> None:
    source = AGENTS_ZSH.read_text(encoding="utf-8")

    assert "_agent_api_key_cache" not in source
    assert "_linux_api_key_cache" not in source
    assert "_read_api_keys_from_linux_keyring" not in source
    assert "_write_api_keys_to_linux_keyring" not in source
    assert "_load_api_keys_from_linux_cache" not in source
    assert "_api_key_cache_available" in source
    assert "_api_key_cache_read" in source
    assert "_api_key_cache_write" in source
    assert "_api_key_cache_load" in source


def test_linux_cache_commands_require_a_service_set(tmp_path: Path) -> None:
    environment, _, _, _ = prepare_fake_commands(tmp_path)

    completed = run_zsh(
        "\n".join(
            [
                '_ensure_command() { command -v "$1" >/dev/null 2>&1 }',
                f"source {shlex.quote(str(AGENTS_ZSH))}",
                "api-key-cache-status",
            ]
        ),
        environment,
    )

    assert completed.returncode == 2
    assert "usage: api-key-cache-status <service>..." in completed.stderr


def test_linux_cache_commands_work_for_any_service_set(tmp_path: Path) -> None:
    environment, keyring_state, _, op_count = prepare_fake_commands(tmp_path)

    completed = run_zsh(
        load_script(
            epilogue="""
api-key-cache-status alpha-api
api-key-cache-refresh alpha-api || exit 1
api-key-cache-status alpha-api
api-key-cache-clear alpha-api || exit 1
api-key-cache-status alpha-api
api-key-cache-status beta-api
"""
        ),
        environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert "API key cache: warm" in completed.stdout
    assert "API key cache: refreshed" in completed.stdout
    assert "API key cache: cleared" in completed.stdout
    assert "API key cache: empty" in completed.stdout
    assert completed.stdout.rstrip().endswith("API key cache: warm")
    assert op_count.read_text(encoding="utf-8").strip() == "2"
    assert not keyring_entry_path(keyring_state, "alpha-api").exists()
    assert keyring_entry_path(keyring_state, "beta-api").exists()

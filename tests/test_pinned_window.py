from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED_WINDOW_SCRIPT = (
    REPO_ROOT / "packages/niri/files/config/niri/bin/pinned-window.sh"
)
REFRESH_COMMAND = "msg plugin xian/pinned-window:state all refresh"


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def prepare_test_environment(
    tmp_path: Path,
    *,
    noctalia_exit_code: int = 0,
) -> tuple[dict[str, str], Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_dir = tmp_path / "runtime"
    notification_log = tmp_path / "noctalia-commands.log"

    write_executable(
        fake_bin / "niri",
        """#!/bin/sh
if [ "$*" = "msg -j focused-window" ]; then
    printf '%s\n' '{"id":42,"app_id":"test.app","title":"Test window"}'
    exit 0
fi
exit 1
""",
    )
    write_executable(
        fake_bin / "noctalia",
        f"""#!/bin/sh
printf '%s\n' "$*" >>"$NOCTALIA_COMMAND_LOG"
exit {noctalia_exit_code}
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "NOCTALIA_COMMAND_LOG": str(notification_log),
        }
    )
    return environment, runtime_dir, notification_log


def run_pinned_window(command: str, environment: dict[str, str]) -> None:
    subprocess.run(
        [PINNED_WINDOW_SCRIPT, command],
        env=environment,
        check=True,
    )


def read_state(runtime_dir: Path) -> dict[str, object]:
    return json.loads(
        (runtime_dir / "niri-pinned-window.json").read_text(encoding="utf-8")
    )


def read_notifications(notification_log: Path) -> list[str]:
    return notification_log.read_text(encoding="utf-8").splitlines()


def test_pin_publishes_state_change_to_noctalia_service(tmp_path: Path) -> None:
    environment, runtime_dir, notification_log = prepare_test_environment(
        tmp_path,
        noctalia_exit_code=17,
    )

    run_pinned_window("pin", environment)

    assert read_state(runtime_dir) == {"pinned": True, "id": "42"}
    assert read_notifications(notification_log) == [REFRESH_COMMAND]


def test_clear_publishes_state_change_to_noctalia_service(tmp_path: Path) -> None:
    environment, runtime_dir, notification_log = prepare_test_environment(tmp_path)
    runtime_dir.mkdir()
    (runtime_dir / "niri-pinned-window.json").write_text(
        '{"pinned":true,"id":"42"}\n',
        encoding="utf-8",
    )

    run_pinned_window("clear", environment)

    assert read_state(runtime_dir) == {"pinned": False, "id": ""}
    assert read_notifications(notification_log) == [REFRESH_COMMAND]


def test_toggle_publishes_each_state_change_to_noctalia_service(tmp_path: Path) -> None:
    environment, runtime_dir, notification_log = prepare_test_environment(tmp_path)

    run_pinned_window("toggle", environment)
    run_pinned_window("toggle", environment)

    assert read_state(runtime_dir) == {"pinned": False, "id": ""}
    assert read_notifications(notification_log) == [REFRESH_COMMAND, REFRESH_COMMAND]

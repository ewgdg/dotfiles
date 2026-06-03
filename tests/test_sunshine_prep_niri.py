import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages/linux/sunshine/files/config/sunshine/sunshine-prep-niri.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("sunshine_prep_niri", MODULE_PATH)
module = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(module)


@pytest.fixture(autouse=True)
def clear_niri_bin_cache() -> None:
    module.niri_bin.cache_clear()


def test_niri_bin_expands_tilde(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("NIRI_BIN", "~/projects/niri/target/release/niri")

    assert module.niri_bin() == "/home/tester/projects/niri/target/release/niri"


def test_niri_msg_uses_configured_niri_binary(monkeypatch) -> None:
    calls = []

    def fake_run_cmd(argv, *, check=True):
        calls.append((argv, check))
        return type("Completed", (), {"stdout": '{"Ok": {"Outputs": []}}'})()

    monkeypatch.setenv("NIRI_SOCKET", "/tmp/niri.sock")
    monkeypatch.setenv("NIRI_BIN", "/opt/niri/bin/niri")
    monkeypatch.setattr(module, "_is_unix_socket", lambda path: path == "/tmp/niri.sock")
    monkeypatch.setattr(module, "command_exists", lambda command: command == "/opt/niri/bin/niri")
    monkeypatch.setattr(module, "run_cmd", fake_run_cmd)

    assert module.niri_msg_json("outputs") == {"Outputs": []}
    assert calls == [(["/opt/niri/bin/niri", "msg", "--json", "outputs"], True)]


def write_output_config(tmp_path: Path, text: str) -> None:
    config_path = tmp_path / "niri" / "cfg" / "output.kdl"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(text, encoding="utf-8")


def test_configured_off_output_names_handles_one_line_blocks(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    write_output_config(
        tmp_path,
        '''
output "DP-1" { off }
output "HDMI-A-1" { mode "1920x1080@60.000" }
output "USB-C-1" { off true }
''',
    )

    assert module.configured_off_output_names() == {"DP-1", "USB-C-1"}


def test_configured_off_output_names_handles_open_and_off_on_same_line(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    write_output_config(
        tmp_path,
        '''
output "DP-1" { off
    mode "1920x1080@60.000"
}
output "HDMI-A-1" {
    off
}
''',
    )

    assert module.configured_off_output_names() == {"DP-1", "HDMI-A-1"}


def test_restore_manually_reenables_disabled_outputs_except_sunshine(monkeypatch) -> None:
    calls = []
    outputs = [
        {"name": "DP-1", "current_mode": None},
        {"name": "eDP-1", "current_mode": {"width": 1920, "height": 1200}},
        {"name": "sunshine", "current_mode": {"width": 3440, "height": 1440}},
        {"name": "HDMI-A-1", "current_mode": None},
    ]

    monkeypatch.setattr(module, "has_niri_bin", lambda: True)
    monkeypatch.setattr(module, "configured_off_output_names", lambda: set())
    monkeypatch.setattr(module, "niri_msg_json", lambda *args: outputs)
    monkeypatch.setattr(module, "niri_msg", lambda *args, check=True: calls.append((args, check)))
    monkeypatch.setattr(module, "kill_runtime_inhibit", lambda: calls.append((("kill-runtime-inhibit",), True)))
    monkeypatch.setattr(module, "suspend_niri_shell_if_active", lambda: False)
    monkeypatch.setattr(module, "resume_suspended_niri_shell", lambda: None)

    module.restore_action(dormant_headless=True, suspend_niri_shell=False)

    assert calls == [
        (("output", "DP-1", "on"), True),
        (("output", "HDMI-A-1", "on"), True),
        (("output", "sunshine", "on"), False),
        (("output", "sunshine", "custom-mode", "3440x1440@60.000"), True),
        (("output", "sunshine", "scale", "1"), True),
        (("kill-runtime-inhibit",), True),
    ]


def test_restore_preserves_configured_off_outputs(monkeypatch) -> None:
    calls = []
    outputs = [
        {"name": "DP-1", "current_mode": None},
        {"name": "HDMI-A-1", "make": "Acme", "model": "Dormant", "serial": "123", "current_mode": None},
        {"name": "sunshine", "current_mode": None},
    ]

    monkeypatch.setattr(module, "has_niri_bin", lambda: True)
    monkeypatch.setattr(module, "configured_off_output_names", lambda: {"Acme Dormant 123"})
    monkeypatch.setattr(module, "niri_msg_json", lambda *args: outputs)
    monkeypatch.setattr(module, "niri_msg", lambda *args, check=True: calls.append((args, check)))
    monkeypatch.setattr(module, "kill_runtime_inhibit", lambda: None)
    monkeypatch.setattr(module, "suspend_niri_shell_if_active", lambda: False)
    monkeypatch.setattr(module, "resume_suspended_niri_shell", lambda: None)

    module.restore_action(dormant_headless=True, suspend_niri_shell=False)

    assert calls == [
        (("output", "DP-1", "on"), True),
        (("output", "sunshine", "on"), False),
        (("output", "sunshine", "scale", "1"), True),
    ]


def test_resume_resets_failed_niri_shell_immediately_before_start(monkeypatch, tmp_path) -> None:
    calls = []
    state_file = tmp_path / "sunshine-niri-shell-suspended.service"
    state_file.write_text("niri-shell.service\n", encoding="utf-8")

    def fake_systemctl(*args):
        calls.append(args)
        return type("Completed", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(module, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "which", lambda cmd: cmd == "systemctl")
    monkeypatch.setattr(module, "_systemctl_user", fake_systemctl)

    assert module.resume_suspended_niri_shell() is True

    assert calls == [
        ("reset-failed", "niri-shell.service"),
        ("start", "niri-shell.service"),
    ]
    assert not state_file.exists()


def test_do_stops_niri_shell_before_headless_output_changes(monkeypatch) -> None:
    calls = []
    outputs = [
        {"name": "sunshine", "current_mode": {"width": 1920, "height": 1080}},
        {"name": "DP-1", "current_mode": {"width": 2560, "height": 1440}},
    ]

    monkeypatch.setattr(module, "require_niri_bin", lambda: calls.append("require-niri"))
    monkeypatch.setattr(module, "which", lambda cmd: False)
    monkeypatch.setattr(module, "suspend_niri_shell_if_active", lambda: calls.append("stop-shell") or True)
    monkeypatch.setattr(module, "resume_suspended_niri_shell", lambda: calls.append("start-shell"))
    monkeypatch.setattr(module, "ensure_headless_output", lambda **kwargs: calls.append("ensure-headless"))
    monkeypatch.setattr(module, "niri_msg_json", lambda *args: outputs)
    monkeypatch.setattr(module, "niri_msg", lambda *args, check=True: calls.append(("niri-msg", args, check)))

    module.do_action(
        width=1920,
        height=1080,
        fps=60,
        output_name=None,
        headless=True,
        solo=True,
        scale_arg=None,
        inhibit=False,
        suspend_niri_shell=True,
    )

    assert calls[:3] == ["require-niri", "stop-shell", "ensure-headless"]
    assert ("niri-msg", ("output", "DP-1", "off"), True) in calls
    assert calls[-1] == "start-shell"


def test_do_restarts_niri_shell_when_prep_fails_after_stop(monkeypatch) -> None:
    calls = []

    def fail_ensure_headless(**kwargs):
        calls.append("ensure-headless")
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "require_niri_bin", lambda: calls.append("require-niri"))
    monkeypatch.setattr(module, "which", lambda cmd: False)
    monkeypatch.setattr(module, "suspend_niri_shell_if_active", lambda: calls.append("stop-shell") or True)
    monkeypatch.setattr(module, "resume_suspended_niri_shell", lambda: calls.append("start-shell"))
    monkeypatch.setattr(module, "ensure_headless_output", fail_ensure_headless)

    with pytest.raises(RuntimeError, match="boom"):
        module.do_action(
            width=1920,
            height=1080,
            fps=60,
            output_name=None,
            headless=True,
            solo=True,
            scale_arg=None,
            inhibit=False,
            suspend_niri_shell=True,
        )

    assert calls == ["require-niri", "stop-shell", "ensure-headless", "start-shell"]


def test_restore_does_not_stop_niri_shell_without_flag(monkeypatch) -> None:
    calls = []
    outputs = [
        {"name": "DP-1", "current_mode": None},
        {"name": "sunshine", "current_mode": {"width": 1920, "height": 1080}},
    ]

    monkeypatch.setattr(module, "has_niri_bin", lambda: True)
    monkeypatch.setattr(module, "configured_off_output_names", lambda: set())
    monkeypatch.setattr(module, "niri_msg_json", lambda *args: outputs)
    monkeypatch.setattr(module, "niri_msg", lambda *args, check=True: calls.append(("niri-msg", args, check)))
    monkeypatch.setattr(module, "suspend_niri_shell_if_active", lambda: calls.append("stop-shell") or True)
    monkeypatch.setattr(module, "kill_runtime_inhibit", lambda: calls.append("kill-runtime-inhibit"))
    monkeypatch.setattr(module, "resume_suspended_niri_shell", lambda: calls.append("start-shell"))

    module.restore_action(dormant_headless=True, suspend_niri_shell=False)

    assert calls == [
        ("niri-msg", ("output", "DP-1", "on"), True),
        ("niri-msg", ("output", "sunshine", "on"), False),
        ("niri-msg", ("output", "sunshine", "custom-mode", "1920x1080@60.000"), True),
        ("niri-msg", ("output", "sunshine", "scale", "1"), True),
        "kill-runtime-inhibit",
        "start-shell",
    ]


def test_restore_stops_niri_shell_around_output_restore_when_flagged(monkeypatch) -> None:
    calls = []
    outputs = [
        {"name": "DP-1", "current_mode": None},
        {"name": "sunshine", "current_mode": {"width": 1920, "height": 1080}},
    ]

    monkeypatch.setattr(module, "has_niri_bin", lambda: True)
    monkeypatch.setattr(module, "configured_off_output_names", lambda: set())
    monkeypatch.setattr(module, "niri_msg_json", lambda *args: outputs)
    monkeypatch.setattr(module, "niri_msg", lambda *args, check=True: calls.append(("niri-msg", args, check)))
    monkeypatch.setattr(module, "suspend_niri_shell_if_active", lambda: calls.append("stop-shell") or True)
    monkeypatch.setattr(module, "kill_runtime_inhibit", lambda: calls.append("kill-runtime-inhibit"))
    monkeypatch.setattr(module, "resume_suspended_niri_shell", lambda: calls.append("start-shell"))

    module.restore_action(dormant_headless=True, suspend_niri_shell=True)

    assert calls == [
        "stop-shell",
        ("niri-msg", ("output", "DP-1", "on"), True),
        ("niri-msg", ("output", "sunshine", "on"), False),
        ("niri-msg", ("output", "sunshine", "custom-mode", "1920x1080@60.000"), True),
        ("niri-msg", ("output", "sunshine", "scale", "1"), True),
        "kill-runtime-inhibit",
        "start-shell",
    ]

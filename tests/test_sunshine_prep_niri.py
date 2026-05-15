import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages/sunshine/files/config/sunshine/sunshine-prep-niri.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("sunshine_prep_niri", MODULE_PATH)
module = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(module)


@pytest.fixture(autouse=True)
def clear_niri_bin_cache() -> None:
    module.niri_bin.cache_clear()


def test_niri_bin_expands_dotman_home_placeholder(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("NIRI_BIN", "%h/projects/niri/target/release/niri")

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

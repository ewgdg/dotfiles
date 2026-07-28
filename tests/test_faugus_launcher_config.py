from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "packages/linux/faugus-launcher"
LOCAL_CONFIG_KEYS = {"donate-last", "playtime", "steamgriddb-api-key"}
MANAGED_CONFIG_KEYS = {
    "accent-color",
    "auto-close-on-launch",
    "automatic-updates",
    "autostart-enabled",
    "background-mode",
    "backup-auto-enabled",
    "backup-dest-dir",
    "backup-frequency",
    "backup-last-date",
    "backup-target-day",
    "banner-enabled",
    "categories-and-sort-enabled",
    "category",
    "cover-size",
    "default-prefix",
    "default-runner",
    "discrete-gpu",
    "gamepad-navigation",
    "gamemode",
    "height",
    "interface-mode",
    "interface-theme",
    "labels-enabled",
    "language",
    "logging-enabled",
    "logging-warning",
    "lossless-location",
    "mangohud",
    "minimized-startup-enabled",
    "mono-icon",
    "no-sleep-enabled",
    "sdl-enabled",
    "show-donate",
    "show-hidden",
    "sort",
    "splash-window-enabled",
    "startup-window-size",
    "steam-user",
    "system-tray",
    "wayland-driver",
    "width",
    "wow64-enabled",
}


def load_package() -> dict:
    with (PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        return tomllib.load(package_file)


def test_package_tracks_v2_json_files() -> None:
    package = load_package()

    config_target = package["targets"]["f_config_faugus_launcher_config_json"]
    environment_target = package["targets"]["f_config_faugus_launcher_envar_json"]

    assert config_target["source"] == "files/config/faugus-launcher/config.json"
    assert config_target["path"] == "~/.config/faugus-launcher/config.json"
    assert environment_target["source"] == "files/config/faugus-launcher/envar.json"
    assert environment_target["path"] == "~/.config/faugus-launcher/envar.json"


def test_config_keeps_local_state_out_of_the_repository() -> None:
    package = load_package()
    local_keys = set(package["vars"]["faugus_launcher"]["config_selectors"])
    config_target = package["targets"]["f_config_faugus_launcher_config_json"]
    config = json.loads(
        (PACKAGE_ROOT / config_target["source"]).read_text(encoding="utf-8")
    )

    assert local_keys == LOCAL_CONFIG_KEYS
    assert local_keys.isdisjoint(config)
    assert set(config) == MANAGED_CONFIG_KEYS
    assert "{{ JSON_RENDER }} --selector-type retain" in config_target["render"]
    assert "{{ JSON_CAPTURE }} --selector-type remove" in config_target["capture"]


def test_managed_v2_preferences_are_portable() -> None:
    package = load_package()
    config_target = package["targets"]["f_config_faugus_launcher_config_json"]
    config = json.loads(
        (PACKAGE_ROOT / config_target["source"]).read_text(encoding="utf-8")
    )
    environment_target = package["targets"]["f_config_faugus_launcher_envar_json"]
    environment = json.loads(
        (PACKAGE_ROOT / environment_target["source"]).read_text(encoding="utf-8")
    )

    assert config["default-prefix"] == "~/Games/prefixes"
    assert config["interface-mode"] == "Grid"
    assert config["system-tray"] == "True"
    assert environment == ["LC_CTYPE=zh_CN.UTF-8"]


def test_json_transform_preserves_only_live_local_values(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    package = load_package()
    config_target = package["targets"]["f_config_faugus_launcher_config_json"]
    repo_config_path = PACKAGE_ROOT / config_target["source"]
    live_config_path = tmp_path / "config.json"
    live_config_path.write_text(
        json.dumps(
            {
                "default-prefix": "/home/tester/Faugus",
                "system-tray": "False",
                "donate-last": "2026-07",
                "playtime": "42",
                "steamgriddb-api-key": "secret",
                "unsupported-setting": "discard",
            }
        ),
        encoding="utf-8",
    )

    rendered = subprocess.run(
        [
            "dotman",
            "transform",
            "json",
            str(live_config_path),
            "--mode",
            "merge",
            "--overlay-file",
            str(repo_config_path),
            "--selector-type",
            "retain",
            "--selectors",
            *sorted(LOCAL_CONFIG_KEYS),
            "--stdout",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    expanded = subprocess.run(
        ["dotman", "rewrite", "home", "expand", "-"],
        input=rendered.stdout,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(expanded.stdout)

    assert config["default-prefix"] == "/home/tester/Games/prefixes"
    assert config["system-tray"] == "True"
    assert config["donate-last"] == "2026-07"
    assert config["playtime"] == "42"
    assert config["steamgriddb-api-key"] == "secret"
    assert "unsupported-setting" not in config

    captured = subprocess.run(
        [
            "dotman",
            "transform",
            "json",
            str(live_config_path),
            "--mode",
            "cleanup",
            "--selector-type",
            "remove",
            "--selectors",
            *sorted(LOCAL_CONFIG_KEYS),
            "--stdout",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    collapsed = subprocess.run(
        ["dotman", "rewrite", "home", "collapse", "-"],
        input=captured.stdout,
        capture_output=True,
        text=True,
        check=True,
    )
    captured_config = json.loads(collapsed.stdout)

    assert captured_config["default-prefix"] == "~/Faugus"
    assert LOCAL_CONFIG_KEYS.isdisjoint(captured_config)

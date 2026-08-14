from __future__ import annotations

from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "packages/deepseek-harness"
LINUX_PACKAGE_ROOT = REPO_ROOT / "packages/linux/deepseek-harness"


def test_package_tracks_only_non_secret_dsh_settings() -> None:
    with (PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    assert package["id"] == "deepseek-harness"
    assert package["depends"] == ["nodejs"]
    assert package["vars"] == {
        "deepseek_harness": {
            "settings_selectors": ["ui-onboarding", "agent-default-model"]
        }
    }
    assert package["targets"] == {
        "f_dsh_settings_yaml": {
            "source": "files/dsh/settings.yaml",
            "path": "~/.dsh/settings.yaml",
            "chmod": "600",
            "render": "{{ YAML_RENDER }} --selector-type retain --selectors {{ vars.deepseek_harness.settings_selectors|shell_args }}",
            "capture": "{{ YAML_CAPTURE }} --selector-type remove --selectors {{ vars.deepseek_harness.settings_selectors|shell_args }}",
        }
    }
    assert not any(
        ".credentials" in target["path"]
        for target in package["targets"].values()
    )


def test_linux_package_installs_dedicated_chrome_app_identity() -> None:
    with (LINUX_PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    assert package == {
        "id": "linux/deepseek-harness",
        "description": "Linux desktop integration for DeepSeek Harness",
        "depends": ["deepseek-harness"],
        "targets": {
            "f_local_bin_dsh": {
                "source": "files/local/bin/dsh",
                "path": "~/.local/bin/dsh",
                "chmod": "755",
            },
            "f_local_share_applications_deepseek_harness_desktop": {
                "source": "files/local/share/applications/deepseek-harness.desktop",
                "path": "~/.local/share/applications/deepseek-harness.desktop",
                "chmod": "644",
            },
            "f_local_share_icons_deepseek_harness_svg": {
                "source": "files/local/share/icons/hicolor/scalable/apps/deepseek-harness.svg",
                "path": "~/.local/share/icons/hicolor/scalable/apps/deepseek-harness.svg",
                "chmod": "644",
                "hooks": {
                    "post_push": 'gtk-update-icon-cache --force --ignore-theme-index "$HOME/.local/share/icons/hicolor"'
                },
            },
        },
        "hooks": {
            "post_push": 'update-desktop-database "$HOME/.local/share/applications"',
        },
    }

    launcher = (LINUX_PACKAGE_ROOT / "files/local/bin/dsh").read_text(
        encoding="utf-8"
    )
    assert '--class="deepseek-harness"' in launcher
    assert '--new-window "$url"' in launcher
    assert "--disable-features=TranslateUI" in launcher
    assert "--user-data-dir=" in launcher
    assert 'flock --nonblock "$instance_lock_fd"' in launcher
    assert '--focus="$url"' in launcher

    desktop_entry = (
        LINUX_PACKAGE_ROOT
        / "files/local/share/applications/deepseek-harness.desktop"
    ).read_text(encoding="utf-8")
    assert "Exec=dsh --app" in desktop_entry
    assert "Terminal=false" in desktop_entry
    assert "NoDisplay=" not in desktop_entry
    assert "Icon=deepseek-harness" in desktop_entry
    assert "StartupWMClass=deepseek-harness" in desktop_entry


def test_app_groups_include_deepseek_harness_packages() -> None:
    with (REPO_ROOT / "groups/apps/ai.toml").open("rb") as group_file:
        ai_group = tomllib.load(group_file)
    with (REPO_ROOT / "groups/apps/linux.toml").open("rb") as group_file:
        linux_group = tomllib.load(group_file)

    assert "deepseek-harness" in ai_group["members"]
    assert "linux/deepseek-harness" in linux_group["members"]

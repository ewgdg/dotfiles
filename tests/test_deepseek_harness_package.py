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
    assert package["depends"] == ["nodejs", "agents"]
    assert package["vars"] == {
        "deepseek_harness": {
            "settings_selectors": [
                "ui-onboarding",
                "agent-default-model",
                "agent-presets",
                "permission",
            ]
        }
    }
    assert package["targets"] == {
        "dsh_install": {
            "sync_policy": "push-only",
            "probe": 'npm_prefix=$(npm prefix --global) || exit 1; if [ -x "$npm_prefix/bin/dsh" ] && "$npm_prefix/bin/dsh" --version >/dev/null 2>&1; then exit 100; fi; exit 0',
            "hooks": {
                "pre_push": "{{ NPM_INSTALL }} --foreground-scripts @deepseek-ai/dsh"
            },
        },
        "dsh_global_instructions": {
            "sync_policy": "push-only",
            "probe": 'sh "$DOTMAN_REPO_ROOT/scripts/manage_relative_symlink.sh" probe "~/.dsh/AGENTS.md" "~/.agents/AGENTS.md"',
            "hooks": {
                "pre_push": 'sh "$DOTMAN_REPO_ROOT/scripts/manage_relative_symlink.sh" apply "~/.dsh/AGENTS.md" "~/.agents/AGENTS.md"'
            },
        },
        "f_dsh_settings_yaml": {
            "source": "files/dsh/settings.yaml",
            "path": "~/.dsh/settings.yaml",
            "chmod": "600",
            "render": "{{ YAML_RENDER }} --selector-type retain --selectors {{ vars.deepseek_harness.settings_selectors|shell_args }}",
            "capture": "{{ YAML_CAPTURE }} --selector-type remove --selectors {{ vars.deepseek_harness.settings_selectors|shell_args }}",
        }
    }
    assert not any(
        ".credentials" in target.get("path", "")
        for target in package["targets"].values()
    )


def test_managed_settings_keep_local_choices_out_of_the_repository() -> None:
    with (PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    settings = (
        PACKAGE_ROOT / package["targets"]["f_dsh_settings_yaml"]["source"]
    ).read_text(encoding="utf-8")
    local_selectors = set(
        package["vars"]["deepseek_harness"]["settings_selectors"]
    )
    managed_top_level_keys = {
        line.split(":", 1)[0]
        for line in settings.splitlines()
        if line and not line.startswith(" ")
    }

    assert local_selectors == {
        "ui-onboarding",
        "agent-default-model",
        "agent-presets",
        "permission",
    }
    assert local_selectors.isdisjoint(managed_top_level_keys)


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

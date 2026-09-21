from __future__ import annotations

import json
import re
from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "packages/devspace"


def load_package() -> dict:
    with (PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        return tomllib.load(package_file)


CONFIG_SOURCE = PACKAGE_ROOT / "files/devspace/config.jsonc"

# The template guards publicBaseUrl so an empty origin renders null rather than an
# invalid empty string. These helpers emulate the two branches of that guard.
GUARDED_VAR = re.compile(r"\{% if .*? %\}(?P<set>.*?)\{% else %\}(?P<unset>.*?)\{% endif %\}")


def render_config(public_base_url: str = "") -> dict:
    text = CONFIG_SOURCE.read_text(encoding="utf-8")
    # The file uses whole-line comments only; strip them to parse it as JSON.
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)

    def substitute(match: re.Match[str]) -> str:
        branch = match.group("set") if public_base_url else match.group("unset")
        return branch.replace("{{ vars.devspace.public_base_url }}", public_base_url)

    return json.loads(GUARDED_VAR.sub(substitute, text))


def test_package_installs_devspace_and_mints_the_owner_token() -> None:
    package = load_package()

    assert package["id"] == "devspace"
    assert package["description"] == "DevSpace MCP coding harness for ChatGPT"
    assert package["depends"] == ["agents", "nodejs"]
    assert package["targets"] == {
        "devspace_install": {
            "sync_policy": "push-only",
            "probe": 'npm_prefix=$(npm prefix --global) || exit 1; if [ -x "$npm_prefix/bin/devspace" ] && "$npm_prefix/bin/devspace" version >/dev/null 2>&1; then exit 100; fi; exit 0',
            "hooks": {"pre_push": "{{ NPM_INSTALL }} @waishnav/devspace"},
        },
        "devspace_owner_token": {
            "sync_policy": "push-only",
            "probe": 'sh "$DOTMAN_PACKAGE_ROOT/scripts/mint_owner_token.sh" probe',
            "hooks": {
                "pre_push": 'sh "$DOTMAN_PACKAGE_ROOT/scripts/mint_owner_token.sh" apply'
            },
        },
        "f_devspace_config": {
            "source": "files/devspace/config.jsonc",
            "path": "~/.devspace/config.jsonc",
            "chmod": "600",
            "preset": "jinja-patch-editor",
        },
    }


def test_owner_password_stays_a_live_local_secret() -> None:
    package = load_package()
    tracked_paths = [target.get("path", "") for target in package["targets"].values()]
    assert not any("auth.json" in path for path in tracked_paths)
    assert "ownerToken" not in json.dumps(render_config())

    script = (PACKAGE_ROOT / "scripts/mint_owner_token.sh").read_text(encoding="utf-8")
    # The hook reports where the secret landed instead of echoing it.
    assert "Read it when ChatGPT asks for approval: cat ${auth_path}" in script
    assert 'echo "${token}"' not in script
    assert 'printf \'{"ownerToken":"%s"}' in script


def test_config_target_renders_through_the_jinja_preset() -> None:
    target = load_package()["targets"]["f_devspace_config"]

    # dotman transform json fails on JSONC comments, so the target renders
    # through the Jinja preset instead of a JSON selector transform.
    assert target["preset"] == "jinja-patch-editor"
    assert (PACKAGE_ROOT / target["source"]).is_file()
    assert "{{ vars.devspace.public_base_url }}" in CONFIG_SOURCE.read_text(encoding="utf-8")


def test_managed_config_pins_instructions_to_the_shared_agents_dir() -> None:
    config = render_config()

    assert config["configVersion"] == 1
    assert config["skills"]["agentDir"] == "~/.agents"
    assert config["server"]["trustProxy"] is True
    assert config["workspaces"]["allowedRoots"] == ["~/Projects"]


def test_public_base_url_defaults_to_the_tunnel_origin() -> None:
    origin = "https://devspace.xianzzz.com"
    assert load_package()["vars"]["devspace"]["public_base_url"] == origin
    assert render_config(origin)["server"]["publicBaseUrl"] == origin

    # An empty var still expresses DevSpace's local-only origin as null.
    assert render_config()["server"]["publicBaseUrl"] is None


def test_linux_package_ships_the_systemd_unit() -> None:
    with (REPO_ROOT / "packages/linux/devspace/package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    assert package["id"] == "linux/devspace"
    assert package["depends"] == ["devspace"]
    assert package["targets"] == {
        "f_etc_systemd_system_devspace_service": {
            "source": "files/etc/systemd/system/devspace.service",
            "path": "/etc/systemd/system/devspace.service",
            "chmod": "644",
            "preset": "jinja-patch-editor",
        }
    }
    assert package["hooks"] == {
        "post_push": ["{{ ENSURE_SYSTEMD }} system devspace.service"]
    }

    unit = (
        REPO_ROOT / "packages/linux/devspace/files/etc/systemd/system/devspace.service"
    ).read_text(encoding="utf-8")
    # A system service does not inherit HOME or the shell PATH, and node comes from
    # the stable fnm alias so a node upgrade cannot break the unit.
    assert "Environment=HOME=/home/{{ vars.host.user }}" in unit
    assert ".local/share/fnm/aliases/default/bin" in unit
    assert "ExecStart=/home/{{ vars.host.user }}/.npm/bin/devspace serve" in unit
    assert "WantedBy=multi-user.target" in unit
    assert "Restart=on-failure" in unit


def test_app_groups_include_the_devspace_packages() -> None:
    with (REPO_ROOT / "groups/apps/ai.toml").open("rb") as group_file:
        ai_group = tomllib.load(group_file)
    with (REPO_ROOT / "groups/apps/linux.toml").open("rb") as group_file:
        linux_group = tomllib.load(group_file)

    assert "devspace" in ai_group["members"]
    assert "linux/devspace" in linux_group["members"]

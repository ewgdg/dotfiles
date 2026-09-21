from __future__ import annotations

import json
import os
import re
import subprocess
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


def test_linux_package_ships_the_user_systemd_unit() -> None:
    with (REPO_ROOT / "packages/linux/devspace/package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    assert package["id"] == "linux/devspace"
    # nodejs is a real dependency: the unit runs on the system node and the shared
    # global npm prefix, so node installation and the ABI rebuild come first.
    # cloudflared is the public connector, pulled in at the Linux layer so hosts
    # without a tunnel keep packages/devspace alone.
    assert package["depends"] == ["devspace", "nodejs", "linux/cloudflared"]
    # The tunnel targets this package also ships are asserted separately.
    assert package["targets"]["f_config_systemd_user_devspace_service"] == {
        "source": "files/config/systemd/user/devspace.service",
        "path": "~/.config/systemd/user/devspace.service",
        "chmod": "644",
    }
    unit = (
        REPO_ROOT
        / "packages/linux/devspace/files/config/systemd/user/devspace.service"
    ).read_text(encoding="utf-8")
    # User scope, on the node inherited from the user manager. Pinning PATH is
    # pointless: Environment= does not expand $PATH, and the manager's PATH already
    # carries ~/.npm/bin and /usr/bin.
    assert "Environment=PATH=" not in unit
    assert "ExecStart=%h/.npm/bin/devspace serve" in unit
    assert "fnm" not in unit
    assert "WantedBy=default.target" in unit
    assert "User=" not in unit
    assert "Restart=on-failure" in unit


def test_app_groups_include_the_devspace_packages() -> None:
    with (REPO_ROOT / "groups/apps/ai.toml").open("rb") as group_file:
        ai_group = tomllib.load(group_file)
    with (REPO_ROOT / "groups/apps/linux.toml").open("rb") as group_file:
        linux_group = tomllib.load(group_file)

    assert "devspace" in ai_group["members"]
    assert "linux/devspace" in linux_group["members"]


def test_linux_package_ships_the_tunnel_that_publishes_the_service() -> None:
    with (REPO_ROOT / "packages/linux/devspace/package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    # The client is a dependency; the unit and ingress are concrete, so they live with
    # the service they publish rather than behind variables in a generic package.
    assert "linux/cloudflared" in package["depends"]
    assert package["targets"]["f_cloudflared_config"] == {
        "source": "files/cloudflared/devspace.yml",
        "path": "~/.cloudflared/devspace.yml",
        "chmod": "600",
        "preset": "jinja-patch-editor",
    }
    assert package["targets"]["f_config_systemd_user_cloudflared_service"] == {
        "source": "files/config/systemd/user/cloudflared.service",
        "path": "~/.config/systemd/user/cloudflared.service",
        "chmod": "644",
    }
    assert package["hooks"]["post_push"] == [
        "{{ ENSURE_SYSTEMD }} user devspace.service",
        "{{ ENSURE_SYSTEMD }} user cloudflared.service",
    ]


def test_tunnel_ingress_follows_the_devspace_origin() -> None:
    config = (
        REPO_ROOT / "packages/linux/devspace/files/cloudflared/devspace.yml"
    ).read_text(encoding="utf-8")

    # Derived from the same var DevSpace advertises for OAuth discovery, so the
    # hostname cannot drift from the origin clients authenticate against.
    assert (
        "hostname: {{ vars.devspace.public_base_url | replace('https://', '') }}"
        in config
    )
    assert "service: http://127.0.0.1:7676" in config
    # Every ingress list needs a catch-all as its last rule.
    assert config.rstrip().endswith("http_status:404")


def test_tunnel_unit_runs_by_name_without_upstreams_service_installer() -> None:
    unit = (
        REPO_ROOT
        / "packages/linux/devspace/files/config/systemd/user/cloudflared.service"
    ).read_text(encoding="utf-8")

    assert "tunnel run devspace" in unit
    # A tunnel-named config, not cloudflared's shared default, so a second tunnel
    # cannot take this one's place.
    assert "--config %h/.cloudflared/devspace.yml" in unit
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", unit)
    # pacman owns the binary; upstream's installer would add a root-owned daily timer
    # running cloudflared update and restart the service behind pacman's back.
    assert "service install" not in unit
    assert "--no-autoupdate" in unit
    assert "WantedBy=default.target" in unit
    assert "User=" not in unit


def run_credentials_script(home: Path, action: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        [
            "sh",
            str(REPO_ROOT / "packages/linux/devspace/scripts/check_tunnel_credentials.sh"),
            action,
        ],
        env=env,
        capture_output=True,
        text=True,
    )


def test_tunnel_credentials_are_reported_and_fail_the_push(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".cloudflared").mkdir(parents=True)

    probe = run_credentials_script(home, "probe")
    assert probe.returncode == 0
    assert "cert.pem" in probe.stderr

    # Logging in is a browser flow, so the apply path fails loudly with what to run
    # instead of letting the unit restart forever on a credential error.
    applied = run_credentials_script(home, "apply")
    assert applied.returncode == 1
    assert "cloudflared tunnel login" in applied.stderr


def test_tunnel_credentials_present_need_no_action(tmp_path: Path) -> None:
    cloudflared_dir = tmp_path / "home/.cloudflared"
    cloudflared_dir.mkdir(parents=True)
    (cloudflared_dir / "cert.pem").write_text("secret\n", encoding="utf-8")
    (cloudflared_dir / "a765117a-57a9-42bc-af1e-b7d48827345f.json").write_text(
        "{}\n", encoding="utf-8"
    )

    assert run_credentials_script(tmp_path / "home", "probe").returncode == 100

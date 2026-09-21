from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "packages/linux/cloudflared"
CREDENTIALS_SCRIPT = PACKAGE_ROOT / "scripts/check_tunnel_credentials.sh"
UNIT_PATH = PACKAGE_ROOT / "files/config/systemd/user/cloudflared.service"
CONFIG_PATH = PACKAGE_ROOT / "files/cloudflared/config.yml"


def run_credentials_script(home: Path, action: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["sh", str(CREDENTIALS_SCRIPT), action],
        env=env,
        capture_output=True,
        text=True,
    )


def test_package_wires_the_tunnel_targets() -> None:
    with (PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    assert package["id"] == "linux/cloudflared"
    # The edge lives in linux/devspace, which selects this package; declaring it
    # here as well would make the two mutually dependent.
    assert "depends" not in package
    assert package["targets"]["cloudflared_installed"] == {
        "sync_policy": "push-only",
        "probe": "{{ PROBE_PACKAGES_INSTALLED }} cloudflared",
        "hooks": {"pre_push": "{{ INSTALL }} cloudflared"},
    }
    assert package["targets"]["f_cloudflared_config"] == {
        "source": "files/cloudflared/config.yml",
        "path": "~/.cloudflared/config.yml",
        "chmod": "600",
    }
    assert package["targets"]["cloudflared_tunnel_credentials"]["probe"] == (
        'sh "$DOTMAN_PACKAGE_ROOT/scripts/check_tunnel_credentials.sh" probe'
    )
    # Without this the post_push hook would enable a unit that was never written.
    assert package["targets"]["f_config_systemd_user_cloudflared_service"] == {
        "source": "files/config/systemd/user/cloudflared.service",
        "path": "~/.config/systemd/user/cloudflared.service",
        "chmod": "644",
    }
    assert package["hooks"] == {
        "post_push": ["{{ ENSURE_SYSTEMD }} user cloudflared.service"]
    }


def test_ingress_hostname_matches_the_devspace_public_origin() -> None:
    with (REPO_ROOT / "packages/devspace/package.toml").open("rb") as package_file:
        devspace = tomllib.load(package_file)

    origin = devspace["vars"]["devspace"]["public_base_url"]
    config = CONFIG_PATH.read_text(encoding="utf-8")

    # DevSpace builds its OAuth discovery URLs from this origin, so a tunnel
    # hostname that drifts from it produces a connector that authenticates nowhere.
    assert f"hostname: {origin.removeprefix('https://')}" in config
    # Every ingress list needs a catch-all as its last rule.
    assert re.search(r"^\s*- service: http_status:404\s*$", config, re.MULTILINE)
    assert config.rstrip().endswith("http_status:404")


def test_unit_runs_by_name_without_upstreams_service_installer() -> None:
    unit = UNIT_PATH.read_text(encoding="utf-8")

    # Selecting the tunnel by name is what keeps a UUID out of the repo.
    assert "tunnel run devspace" in unit
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", unit)
    # pacman owns the binary; upstream's installer would add a root-owned daily
    # timer running `cloudflared update`, replacing /usr/bin/cloudflared behind
    # pacman's back.
    assert "service install" not in unit
    assert "--no-autoupdate" in unit
    # User scope, like the devspace unit: no elevation, and greetd keeps the user
    # manager alive.
    assert "WantedBy=default.target" in unit
    assert "User=" not in unit


def test_missing_credentials_are_reported_and_fail_the_push(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".cloudflared").mkdir(parents=True)

    probe = run_credentials_script(home, "probe")
    assert probe.returncode == 0
    assert "cert.pem" in probe.stderr

    # The apply path cannot log in for you, so it fails loudly with the commands
    # instead of letting the unit restart forever on a credential error.
    applied = run_credentials_script(home, "apply")
    assert applied.returncode == 1
    assert "cloudflared tunnel login" in applied.stderr
    assert "cloudflared tunnel create devspace" in applied.stderr
    assert "cloudflared tunnel route dns" in applied.stderr


def test_present_credentials_need_no_action(tmp_path: Path) -> None:
    cloudflared_dir = tmp_path / "home/.cloudflared"
    cloudflared_dir.mkdir(parents=True)
    (cloudflared_dir / "cert.pem").write_text("secret\n", encoding="utf-8")
    (cloudflared_dir / "a765117a-57a9-42bc-af1e-b7d48827345f.json").write_text(
        "{}\n", encoding="utf-8"
    )

    probe = run_credentials_script(tmp_path / "home", "probe")
    assert probe.returncode == 100


def test_linux_group_ships_the_tunnel_next_to_devspace() -> None:
    with (REPO_ROOT / "groups/apps/linux.toml").open("rb") as group_file:
        members = tomllib.load(group_file)["members"]

    assert "linux/cloudflared" in members
    assert "linux/devspace" in members

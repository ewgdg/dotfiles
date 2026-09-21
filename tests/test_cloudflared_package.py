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


def run_credentials_script(
    home: Path, action: str, tunnel_name: str = "example"
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["sh", str(CREDENTIALS_SCRIPT), action, tunnel_name],
        env=env,
        capture_output=True,
        text=True,
    )


def test_package_wires_the_tunnel_targets() -> None:
    with (PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    assert package["id"] == "linux/cloudflared"
    # What a tunnel publishes is host-specific, so it is a var rather than a literal.
    assert package["vars"]["cloudflared"] == {
        "tunnel_name": "",
        "hostname": "",
        "local_service": "",
    }
    assert package["targets"]["cloudflared_installed"] == {
        "sync_policy": "push-only",
        "probe": "{{ PROBE_PACKAGES_INSTALLED }} cloudflared",
        "hooks": {"pre_push": "{{ INSTALL }} cloudflared"},
    }
    assert package["targets"]["f_cloudflared_config"] == {
        "source": "files/cloudflared/config.yml",
        "path": "~/.cloudflared/config.yml",
        "chmod": "600",
        "preset": "jinja-patch-editor",
    }
    # The tunnel name is passed in, so the script needs no configuration of its own.
    credentials_hook = 'sh "$DOTMAN_PACKAGE_ROOT/scripts/check_tunnel_credentials.sh"'
    assert package["targets"]["cloudflared_tunnel_credentials"] == {
        "sync_policy": "push-only",
        "probe": credentials_hook + ' probe "{{ vars.cloudflared.tunnel_name }}"',
        "hooks": {
            "pre_push": credentials_hook + ' apply "{{ vars.cloudflared.tunnel_name }}"'
        },
    }
    # Without this the post_push hook would enable a unit that was never written.
    assert package["targets"]["f_config_systemd_user_cloudflared_service"] == {
        "source": "files/config/systemd/user/cloudflared.service",
        "path": "~/.config/systemd/user/cloudflared.service",
        "chmod": "644",
        "preset": "jinja-patch-editor",
    }
    assert package["hooks"] == {
        "post_push": ["{{ ENSURE_SYSTEMD }} user cloudflared.service"]
    }


def test_package_knows_no_particular_tunnel() -> None:
    """A host names its tunnel; this package must stay reusable for other ones."""
    for path in sorted(PACKAGE_ROOT.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8").lower()
            assert "devspace" not in text, f"{path} names a specific tunnel"


def test_config_is_ingress_only_and_driven_by_vars() -> None:
    config = CONFIG_PATH.read_text(encoding="utf-8")

    assert "hostname: {{ vars.cloudflared.hostname }}" in config
    assert "service: {{ vars.cloudflared.local_service }}" in config
    # Every ingress list needs a catch-all as its last rule.
    assert config.rstrip().endswith("http_status:404")
    # A UUID or credentials-file here would mean the name is not being passed in.
    assert "credentials-file" not in config
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", config)


def test_unit_runs_by_name_without_upstreams_service_installer() -> None:
    unit = UNIT_PATH.read_text(encoding="utf-8")

    assert "tunnel run {{ vars.cloudflared.tunnel_name }}" in unit
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", unit)
    # The system package manager owns the binary; upstream's installer would add a
    # root-owned daily timer running "cloudflared update" and restart the service.
    assert "service install" not in unit
    assert "--no-autoupdate" in unit
    # User scope: no elevation, and the display manager keeps the user manager alive.
    assert "WantedBy=default.target" in unit
    assert "User=" not in unit


def test_missing_credentials_are_reported_and_fail_the_push(tmp_path: Path) -> None:
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


def test_unconfigured_host_is_reported_rather_than_started(tmp_path: Path) -> None:
    cloudflared_dir = tmp_path / "home/.cloudflared"
    cloudflared_dir.mkdir(parents=True)
    (cloudflared_dir / "cert.pem").write_text("secret\n", encoding="utf-8")
    (cloudflared_dir / "a765117a-57a9-42bc-af1e-b7d48827345f.json").write_text(
        "{}\n", encoding="utf-8"
    )

    # Credentials exist, but a host that never named a tunnel cannot run the unit.
    unconfigured = run_credentials_script(tmp_path / "home", "probe", "")
    assert unconfigured.returncode == 0
    assert "tunnel-name" in unconfigured.stderr

    configured = run_credentials_script(tmp_path / "home", "probe", "example")
    assert configured.returncode == 100

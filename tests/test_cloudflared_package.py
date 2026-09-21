from __future__ import annotations

from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "packages/linux/cloudflared"


def test_package_installs_the_client_only() -> None:
    with (PACKAGE_ROOT / "package.toml").open("rb") as package_file:
        package = tomllib.load(package_file)

    assert package["id"] == "linux/cloudflared"
    # A tunnel is concrete, so its unit and ingress live with the service it
    # publishes. Nothing here needs configuring, so there are no vars either.
    assert list(package["targets"]) == ["cloudflared_installed"]
    assert package["targets"]["cloudflared_installed"] == {
        "sync_policy": "push-only",
        "probe": "{{ PROBE_PACKAGES_INSTALLED }} cloudflared",
        "hooks": {"pre_push": "{{ INSTALL }} cloudflared"},
    }
    assert "vars" not in package
    assert "hooks" not in package


def test_package_knows_no_particular_service_or_tunnel() -> None:
    """A tunnel is owned by the package that publishes a service, not this one."""
    for path in sorted(PACKAGE_ROOT.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8").lower()
            assert "devspace" not in text, f"{path} names a specific service"

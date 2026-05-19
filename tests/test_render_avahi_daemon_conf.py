from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "packages/linux/avahi/scripts/render_avahi_daemon_conf.py"


def make_interface(sys_class_net: Path, name: str, *, physical: bool, interface_type: int = 1, wireless: bool = False) -> None:
    interface_path = sys_class_net / name
    interface_path.mkdir(parents=True)
    (interface_path / "type").write_text(f"{interface_type}\n", encoding="utf-8")
    if physical:
        (interface_path / "device").mkdir()
    if wireless:
        (interface_path / "wireless").mkdir()


def run_render(tmp_path: Path, repo_path: Path, sys_class_net: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            str(SCRIPT_PATH),
            "render",
            str(repo_path),
            "--sys-class-net",
            str(sys_class_net),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_render_allows_only_physical_lan_interfaces(tmp_path: Path) -> None:
    sys_class_net = tmp_path / "sys/class/net"
    make_interface(sys_class_net, "lo", physical=False)
    make_interface(sys_class_net, "docker0", physical=False)
    make_interface(sys_class_net, "veth123", physical=False)
    make_interface(sys_class_net, "enp7s0", physical=True)
    make_interface(sys_class_net, "wlp8s0", physical=True, wireless=True)

    repo_path = tmp_path / "repo.conf"
    repo_path.write_text(
        "[server]\nuse-ipv4=yes\n#allow-interfaces=eth0\nallow-interfaces=__DOTMAN_AVAHI_ALLOWED_INTERFACES__\n[publish]\npublish-workstation=no\n",
        encoding="utf-8",
    )

    completed = run_render(tmp_path, repo_path, sys_class_net)

    assert completed.returncode == 0, completed.stderr
    assert "#allow-interfaces=eth0" in completed.stdout
    assert "allow-interfaces=enp7s0,wlp8s0" in completed.stdout
    assert "docker0" not in completed.stdout
    assert "veth123" not in completed.stdout
    assert "use-ipv4=yes" in completed.stdout
    assert "publish-workstation=no" in completed.stdout


def test_render_refuses_when_no_physical_lan_interface_exists(tmp_path: Path) -> None:
    sys_class_net = tmp_path / "sys/class/net"
    make_interface(sys_class_net, "lo", physical=False)
    make_interface(sys_class_net, "docker0", physical=False)

    repo_path = tmp_path / "repo.conf"
    repo_path.write_text("[server]\nallow-interfaces=__DOTMAN_AVAHI_ALLOWED_INTERFACES__\n", encoding="utf-8")

    completed = run_render(tmp_path, repo_path, sys_class_net)

    assert completed.returncode == 1
    assert "no physical Ethernet/Wi-Fi interfaces found" in completed.stderr


def test_capture_keeps_repo_source_machine_independent(tmp_path: Path) -> None:
    live_path = tmp_path / "live.conf"
    live_path.write_text(
        "[server]\nuse-ipv4=yes\n#allow-interfaces=eth0\nallow-interfaces=enp7s0,wlp8s0\n[publish]\npublish-workstation=no\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            str(SCRIPT_PATH),
            "capture",
            str(live_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "#allow-interfaces=eth0" in completed.stdout
    assert "allow-interfaces=__DOTMAN_AVAHI_ALLOWED_INTERFACES__" in completed.stdout
    assert "enp7s0" not in completed.stdout
    assert "wlp8s0" not in completed.stdout
    assert "use-ipv4=yes" in completed.stdout
    assert "publish-workstation=no" in completed.stdout

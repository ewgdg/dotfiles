from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_APPS_SCRIPT = REPO_ROOT / "packages/browser/scripts/web_apps.py"
EXPORTED_ICON_SIZES = (16, 32, 48, 128, 256)
PROBE_ACTION_NEEDED = 0
PROBE_NOOP = 100

# Mirrors ChatGPT's favicon: the only fill comes from embedded CSS, which
# Qt-based shells ignore, so installing it as-is shows a blank icon.
CSS_FILLED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
<style>:root { fill: #000; } @media (prefers-color-scheme: dark) { :root { fill: #fff; } }</style>
<path d="M4 4h16v16H4z"/>
</svg>
"""


def run_web_apps(
    command: str, spec_path: Path, data_home: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WEB_APPS_SCRIPT), command, str(spec_path)],
        env={**os.environ, "XDG_DATA_HOME": str(data_home)},
        capture_output=True,
        text=True,
        timeout=60,
    )


def write_spec(tmp_path: Path, icon_path: Path) -> Path:
    spec_path = tmp_path / "web-apps.toml"
    spec_path.write_text(
        f"""
[[apps]]
id = "chatgpt"
name = "ChatGPT Web"
url = "https://chatgpt.com/"
icon = "{icon_path.as_uri()}"
""",
        encoding="utf-8",
    )
    return spec_path


def icon_is_visible(icon_path: Path) -> bool:
    opaque = subprocess.run(
        ["magick", str(icon_path), "-format", "%[fx:maxima.a]", "info:"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return float(opaque) > 0


@pytest.fixture
def css_filled_svg(tmp_path: Path) -> Path:
    icon_path = tmp_path / "icon.svg"
    icon_path.write_text(CSS_FILLED_SVG, encoding="utf-8")
    return icon_path


@pytest.fixture
def raster_png(tmp_path: Path, css_filled_svg: Path) -> Path:
    icon_path = tmp_path / "icon.png"
    subprocess.run(
        ["rsvg-convert", "-w", "512", "-h", "512", "-o", str(icon_path), str(css_filled_svg)],
        check=True,
    )
    return icon_path


def test_desktop_entry_matches_chrome_app_window_identity(
    tmp_path: Path, css_filled_svg: Path
) -> None:
    data_home = tmp_path / "share"
    run_web_apps("apply", write_spec(tmp_path, css_filled_svg), data_home).check_returncode()

    entry = (data_home / "applications/webapp-chatgpt.desktop").read_text(encoding="utf-8")

    assert "Name=ChatGPT Web\n" in entry
    assert (
        'Exec=google-chrome-stable --profile-directory=Default "--app=https://chatgpt.com/"\n'
        in entry
    )
    assert "Icon=webapp-chatgpt\n" in entry
    # Chrome's Wayland app_id for --app windows; niri rules match on it.
    assert "StartupWMClass=chrome-chatgpt.com__-Default\n" in entry


@pytest.mark.parametrize("icon_fixture", ["css_filled_svg", "raster_png"])
def test_apply_installs_visible_png_icons_at_chrome_sizes(
    tmp_path: Path, icon_fixture: str, request: pytest.FixtureRequest
) -> None:
    data_home = tmp_path / "share"
    spec_path = write_spec(tmp_path, request.getfixturevalue(icon_fixture))

    run_web_apps("apply", spec_path, data_home).check_returncode()

    hicolor = data_home / "icons/hicolor"
    assert not list(hicolor.rglob("*.svg"))
    for size in EXPORTED_ICON_SIZES:
        icon_path = hicolor / f"{size}x{size}/apps/webapp-chatgpt.png"
        assert icon_is_visible(icon_path)


def test_probe_reports_missing_then_current_state(
    tmp_path: Path, css_filled_svg: Path
) -> None:
    data_home = tmp_path / "share"
    spec_path = write_spec(tmp_path, css_filled_svg)

    assert run_web_apps("probe", spec_path, data_home).returncode == PROBE_ACTION_NEEDED
    run_web_apps("apply", spec_path, data_home).check_returncode()
    assert run_web_apps("probe", spec_path, data_home).returncode == PROBE_NOOP


def test_apply_removes_launchers_dropped_from_spec_only(
    tmp_path: Path, css_filled_svg: Path
) -> None:
    data_home = tmp_path / "share"
    spec_path = write_spec(tmp_path, css_filled_svg)
    applications = data_home / "applications"
    stale_icon = data_home / "icons/hicolor/48x48/apps/webapp-dropped.png"
    unowned_entry = applications / "chrome-abc-Default.desktop"
    run_web_apps("apply", spec_path, data_home).check_returncode()
    (applications / "webapp-dropped.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")
    stale_icon.write_bytes(b"")
    unowned_entry.write_text("[Desktop Entry]\n", encoding="utf-8")

    assert run_web_apps("probe", spec_path, data_home).returncode == PROBE_ACTION_NEEDED
    run_web_apps("apply", spec_path, data_home).check_returncode()

    assert not (applications / "webapp-dropped.desktop").exists()
    assert not stale_icon.exists()
    assert unowned_entry.exists()
    assert (applications / "webapp-chatgpt.desktop").exists()
    assert run_web_apps("probe", spec_path, data_home).returncode == PROBE_NOOP


def test_probe_detects_changed_spec(tmp_path: Path, css_filled_svg: Path, raster_png: Path) -> None:
    data_home = tmp_path / "share"
    run_web_apps("apply", write_spec(tmp_path, css_filled_svg), data_home).check_returncode()

    changed_icon_spec = write_spec(tmp_path, raster_png)

    assert run_web_apps("probe", changed_icon_spec, data_home).returncode == PROBE_ACTION_NEEDED

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_APPS_SCRIPT = REPO_ROOT / "packages/browser/scripts/web_apps.py"
EXPORTED_ICON_SIZES = (16, 32, 48, 128, 256)
PROBE_ACTION_NEEDED = 0
PROBE_NOOP = 100

# Mirrors ChatGPT's favicon: the only fill comes from embedded CSS, which
# Qt-based shells ignore, so installing it as-is shows a blank icon. Its
# dark-mode rule only applies in renderers that evaluate `@media`.
CSS_FILLED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
<style>:root { fill: #000; } @media (prefers-color-scheme: dark) { :root { fill: #fff; } }</style>
<path d="M4 4h16v16H4z"/>
</svg>
"""


def run_web_apps(
    command: str, spec_path: Path, data_home: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WEB_APPS_SCRIPT), command, str(spec_path), *arguments],
        env={**os.environ, "XDG_DATA_HOME": str(data_home)},
        capture_output=True,
        text=True,
        timeout=60,
    )


def write_spec(tmp_path: Path, icon_source: Path | None) -> Path:
    """Write a ChatGPT spec, with its committed icon copied next to it."""
    spec_path = tmp_path / "web-apps.toml"
    spec_path.write_text(
        """
[[apps]]
id = "chatgpt"
name = "ChatGPT Web"
url = "https://chatgpt.com/"
""",
        encoding="utf-8",
    )
    if icon_source:
        icons_dir = tmp_path / "icons"
        icons_dir.mkdir(exist_ok=True)
        shutil.copy(icon_source, icons_dir / f"chatgpt{icon_source.suffix}")
    return spec_path


def icon_channel_maximum(icon_path: Path, channel: str) -> float:
    return float(
        subprocess.run(
            ["magick", str(icon_path), "-format", f"%[fx:maxima.{channel}]", "info:"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )


def icon_is_visible(icon_path: Path) -> bool:
    return icon_channel_maximum(icon_path, "a") > 0


def solid_png(path: Path, color: str) -> Path:
    subprocess.run(["magick", "-size", "64x64", f"xc:{color}", str(path)], check=True)
    return path


def center_color(icon_path: Path) -> str:
    return subprocess.run(
        ["magick", str(icon_path), "-format", "%[pixel:p{24,24}]", "info:"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture
def css_filled_svg(tmp_path: Path) -> Path:
    icon_path = tmp_path / "source.svg"
    icon_path.write_text(CSS_FILLED_SVG, encoding="utf-8")
    return icon_path


@pytest.fixture
def raster_png(tmp_path: Path) -> Path:
    icon_path = tmp_path / "source.png"
    subprocess.run(
        ["magick", "-size", "512x512", "xc:none", "-fill", "black",
         "-draw", "rectangle 64,64 448,448", str(icon_path)],
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


def test_svg_icons_render_dark_mode_variant(tmp_path: Path, css_filled_svg: Path) -> None:
    data_home = tmp_path / "share"

    run_web_apps("apply", write_spec(tmp_path, css_filled_svg), data_home).check_returncode()

    icon_path = data_home / "icons/hicolor/48x48/apps/webapp-chatgpt.png"
    assert icon_channel_maximum(icon_path, "r") == 1


def test_probe_reports_missing_then_current_state(
    tmp_path: Path, css_filled_svg: Path
) -> None:
    data_home = tmp_path / "share"
    spec_path = write_spec(tmp_path, css_filled_svg)

    assert run_web_apps("probe", spec_path, data_home).returncode == PROBE_ACTION_NEEDED
    run_web_apps("apply", spec_path, data_home).check_returncode()
    assert run_web_apps("probe", spec_path, data_home).returncode == PROBE_NOOP


def test_probe_detects_changed_icon_source(tmp_path: Path, css_filled_svg: Path) -> None:
    data_home = tmp_path / "share"
    spec_path = write_spec(tmp_path, css_filled_svg)
    run_web_apps("apply", spec_path, data_home).check_returncode()

    committed_icon = tmp_path / "icons/chatgpt.svg"
    committed_icon.write_text(CSS_FILLED_SVG.replace("M4 4h16", "M2 2h20"), encoding="utf-8")

    assert run_web_apps("probe", spec_path, data_home).returncode == PROBE_ACTION_NEEDED


def test_probe_fails_hard_when_icon_source_is_missing(tmp_path: Path) -> None:
    data_home = tmp_path / "share"

    completed = run_web_apps("probe", write_spec(tmp_path, None), data_home)

    assert completed.returncode not in (PROBE_ACTION_NEEDED, PROBE_NOOP)
    assert "chatgpt" in completed.stderr


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


def write_manifest_site(site_dir: Path) -> str:
    """Serve a page whose manifest lists icons coloured by how Chrome ranks them."""
    site_dir.mkdir()
    solid_png(site_dir / "small.png", "red")
    solid_png(site_dir / "large.png", "blue")
    solid_png(site_dir / "maskable.png", "lime")
    (site_dir / "app.webmanifest").write_text(
        """{"icons": [
  {"src": "small.png", "sizes": "48x48", "type": "image/png"},
  {"src": "large.png", "sizes": "192x192 512x512", "type": "image/png"},
  {"src": "maskable.png", "sizes": "1024x1024", "purpose": "maskable"}
]}""",
        encoding="utf-8",
    )
    (site_dir / "index.html").write_text(
        '<html><head><link rel="manifest" href="app.webmanifest"></head></html>',
        encoding="utf-8",
    )
    return (site_dir / "index.html").as_uri()


def write_site_spec(tmp_path: Path, url: str, icon_line: str = "") -> Path:
    spec_path = tmp_path / "web-apps.toml"
    spec_path.write_text(
        f"""
[[apps]]
id = "site"
name = "Site Web"
url = "{url}"
{icon_line}
""",
        encoding="utf-8",
    )
    return spec_path


def test_fetch_saves_largest_any_purpose_manifest_icon(tmp_path: Path) -> None:
    url = write_manifest_site(tmp_path / "site")

    completed = run_web_apps("fetch", write_site_spec(tmp_path, url), tmp_path / "share", "site")

    completed.check_returncode()
    assert center_color(tmp_path / "icons/site.png") == "srgb(0,0,255)"


def test_fetch_icon_url_overrides_manifest(tmp_path: Path) -> None:
    url = write_manifest_site(tmp_path / "site")
    override = solid_png(tmp_path / "override.png", "yellow")
    spec_path = write_site_spec(tmp_path, url, f'icon = "{override.as_uri()}"')

    run_web_apps("fetch", spec_path, tmp_path / "share", "site").check_returncode()

    assert center_color(tmp_path / "icons/site.png") == "srgb(255,255,0)"


def test_fetch_fails_when_site_has_no_manifest_and_no_icon(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><head></head></html>", encoding="utf-8")

    completed = run_web_apps(
        "fetch", write_site_spec(tmp_path, page.as_uri()), tmp_path / "share", "site"
    )

    assert completed.returncode != 0
    assert "icon" in completed.stderr
    assert not (tmp_path / "icons").exists()

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_APPS_SCRIPT = REPO_ROOT / "packages/browser/scripts/web_apps.py"
ICON_SIZE = 256

# Mirrors ChatGPT's favicon: the only fill comes from embedded CSS, which
# Qt-based shells ignore, so installing it as-is shows a blank icon. Its
# dark-mode rule only applies in renderers that evaluate `@media`.
CSS_FILLED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
<style>:root { fill: #000; } @media (prefers-color-scheme: dark) { :root { fill: #fff; } }</style>
<path d="M4 4h16v16H4z"/>
</svg>
"""


def run_add(
    files_dir: Path, app_id: str, name: str, url: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WEB_APPS_SCRIPT), "add", "--files-dir", str(files_dir),
         app_id, name, url, *arguments],
        capture_output=True,
        text=True,
        timeout=60,
    )


def desktop_path(files_dir: Path, app_id: str) -> Path:
    return files_dir / f"local/share/applications/webapp-{app_id}.desktop"


def icon_path(files_dir: Path, app_id: str) -> Path:
    return files_dir / f"local/share/icons/hicolor/{ICON_SIZE}x{ICON_SIZE}/apps/webapp-{app_id}.png"


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


def icon_dimensions(icon_path: Path) -> str:
    return subprocess.run(
        ["magick", str(icon_path), "-format", "%wx%h", "info:"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_desktop_entry_matches_chrome_app_window_identity(
    tmp_path: Path, css_filled_svg: Path
) -> None:
    files_dir = tmp_path / "files"
    run_add(
        files_dir, "chatgpt", "ChatGPT Web", "https://chatgpt.com/", "--icon", str(css_filled_svg)
    ).check_returncode()

    entry = desktop_path(files_dir, "chatgpt").read_text(encoding="utf-8")

    assert "Name=ChatGPT Web\n" in entry
    assert (
        'Exec=google-chrome-stable --profile-directory=Default "--app=https://chatgpt.com/"\n'
        in entry
    )
    assert "Icon=webapp-chatgpt\n" in entry
    # Chrome's Wayland app_id for --app windows; niri rules match on it.
    assert "StartupWMClass=chrome-chatgpt.com__-Default\n" in entry


@pytest.mark.parametrize("icon_fixture", ["css_filled_svg", "raster_png"])
def test_add_writes_one_visible_png_icon(
    tmp_path: Path, icon_fixture: str, request: pytest.FixtureRequest
) -> None:
    files_dir = tmp_path / "files"

    run_add(
        files_dir, "chatgpt", "ChatGPT Web", "https://chatgpt.com/",
        "--icon", str(request.getfixturevalue(icon_fixture)),
    ).check_returncode()

    icons = list((files_dir / "local/share/icons").rglob("*.*"))
    assert icons == [icon_path(files_dir, "chatgpt")]
    assert icon_dimensions(icons[0]) == f"{ICON_SIZE}x{ICON_SIZE}"
    assert icon_is_visible(icons[0])


def test_regenerated_icon_is_byte_identical(tmp_path: Path, raster_png: Path) -> None:
    """Icons are committed, so unchanged sources must not produce a git diff."""
    files_dir = tmp_path / "files"
    add_arguments = (files_dir, "chatgpt", "ChatGPT Web", "https://chatgpt.com/", "--icon", str(raster_png))
    run_add(*add_arguments).check_returncode()
    first_icon = icon_path(files_dir, "chatgpt").read_bytes()
    time.sleep(1.1)

    run_add(*add_arguments).check_returncode()

    assert icon_path(files_dir, "chatgpt").read_bytes() == first_icon


def test_svg_icons_render_dark_mode_variant(tmp_path: Path, css_filled_svg: Path) -> None:
    files_dir = tmp_path / "files"

    run_add(
        files_dir, "chatgpt", "ChatGPT Web", "https://chatgpt.com/", "--icon", str(css_filled_svg)
    ).check_returncode()

    assert icon_channel_maximum(icon_path(files_dir, "chatgpt"), "r") == 1


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


def test_add_without_icon_uses_largest_any_purpose_manifest_icon(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    url = write_manifest_site(tmp_path / "site")

    run_add(files_dir, "site", "Site Web", url).check_returncode()

    assert center_color(icon_path(files_dir, "site")) == "srgb(0,0,255)"
    assert desktop_path(files_dir, "site").is_file()


def test_add_fails_without_writing_when_site_has_no_manifest(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    page = tmp_path / "index.html"
    page.write_text("<html><head></head></html>", encoding="utf-8")

    completed = run_add(files_dir, "site", "Site Web", page.as_uri())

    assert completed.returncode != 0
    assert "icon" in completed.stderr
    assert not files_dir.exists()

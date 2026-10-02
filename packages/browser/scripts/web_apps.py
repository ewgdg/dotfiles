#!/usr/bin/env python3
"""
web_apps.py - Generate a Chrome `--app` launcher into the browser package.

add: write `webapp-<id>.desktop` and one 256px PNG icon under the package's
`files/`, where dotman tracks them. The icon comes from `--icon` (a path or
URL) or, without it, from the site's web app manifest. Re-running `add` regenerates the app.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request


CHROME_COMMAND = "google-chrome-stable"
CHROME_PROFILE_DIRECTORY = "Default"
LAUNCHER_FILE_PREFIX = "webapp-"
# One size only: icon themes scale the nearest size for every other request.
ICON_SIZE = 256
PACKAGE_FILES_DIR = Path(__file__).resolve().parents[1] / "files"
CHROME_RENDER_TIMEOUT_SECONDS = 60
# Scales the SVG to the screenshot window; on its own Chrome would draw it at
# its intrinsic size and crop it.
SVG_WRAPPER_HTML = """<!doctype html>
<style>html, body { margin: 0; height: 100%; overflow: hidden; } img { display: block; width: 100%; height: 100%; object-fit: contain; }</style>
<img src="icon.svg">
"""
# Some icon CDNs reject urllib's default user agent.
DOWNLOAD_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Chrome/140 Safari/537.36"
DOWNLOAD_TIMEOUT_SECONDS = 30
# Characters the desktop entry spec cannot carry inside a quoted Exec argument
# without extra escaping; URLs never need them.
UNQUOTABLE_EXEC_CHARACTERS = frozenset('"`$\\')


@dataclass(frozen=True)
class WebApp:
    id: str
    name: str
    url: str


@dataclass(frozen=True)
class LauncherFiles:
    """Paths of one app's launcher files, mirroring their live paths under `files/`."""

    desktop_path: Path
    icon_path: Path

    @classmethod
    def under(cls, files_dir: Path, app: WebApp) -> LauncherFiles:
        file_stem = f"{LAUNCHER_FILE_PREFIX}{app.id}"
        return cls(
            files_dir / f"local/share/applications/{file_stem}.desktop",
            files_dir / f"local/share/icons/hicolor/{ICON_SIZE}x{ICON_SIZE}/apps/{file_stem}.png",
        )


def chrome_app_window_class(url: str) -> str:
    """Return the app_id Chrome gives `--app=<url>` windows.

    Chrome names the app `<host>_<path>` with `/` replaced by `_`, e.g.
    `https://chatgpt.com/` runs as `chrome-chatgpt.com__-Default`.
    """
    parsed_url = urllib.parse.urlsplit(url)
    app_name = f"{parsed_url.hostname}_{parsed_url.path}".replace("/", "_")
    return f"chrome-{app_name}-{CHROME_PROFILE_DIRECTORY}"


def quote_exec_argument(argument: str) -> str:
    if UNQUOTABLE_EXEC_CHARACTERS & set(argument):
        raise ValueError(f"unsupported character in Exec argument: {argument}")
    # Quoted so `&`, `?` and `#` survive; `%` is a field code unless doubled.
    return '"' + argument.replace("%", "%%") + '"'


def render_desktop_entry(app: WebApp) -> str:
    exec_command = " ".join(
        [
            CHROME_COMMAND,
            f"--profile-directory={CHROME_PROFILE_DIRECTORY}",
            quote_exec_argument(f"--app={app.url}"),
        ]
    )
    return "\n".join(
        [
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            f"Name={app.name}",
            f"Exec={exec_command}",
            f"Icon={LAUNCHER_FILE_PREFIX}{app.id}",
            f"StartupWMClass={chrome_app_window_class(app.url)}",
            "Terminal=false",
            "StartupNotify=true",
            "Categories=Network;",
            "",
        ]
    )


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read()


class ManifestLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.manifest_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        rel_values = (attributes.get("rel") or "").lower().split()
        if tag == "link" and "manifest" in rel_values and self.manifest_href is None:
            self.manifest_href = attributes.get("href")


def manifest_icon_rank(icon: dict) -> tuple[bool, int]:
    """Rank like Chrome: SVG (or `sizes: any`) first, then the largest size."""
    sizes = icon.get("sizes", "").lower().split()
    is_scalable = "any" in sizes or icon.get("type") == "image/svg+xml" or icon["src"].endswith(".svg")
    largest_edge = max(
        (int(size.split("x")[0]) for size in sizes if "x" in size), default=0
    )
    return is_scalable, largest_edge


def discover_manifest_icon_url(app: WebApp) -> str:
    """Return the best launcher icon from the site's web app manifest."""
    parser = ManifestLinkParser()
    parser.feed(download(app.url).decode("utf-8", errors="replace"))
    if not parser.manifest_href:
        raise RuntimeError(f"{app.id}: {app.url} links no web app manifest; add an icon by hand")
    manifest_url = urllib.parse.urljoin(app.url, parser.manifest_href)
    manifest = json.loads(download(manifest_url))
    # Maskable/monochrome-only icons are cropped or flat; launchers need `any`.
    launcher_icons = [
        icon
        for icon in manifest.get("icons", [])
        if "any" in icon.get("purpose", "any").split()
    ]
    if not launcher_icons:
        raise RuntimeError(f"{app.id}: {manifest_url} has no `any` purpose icon; add an icon by hand")
    best_icon = max(launcher_icons, key=manifest_icon_rank)
    return urllib.parse.urljoin(manifest_url, best_icon["src"])


def is_svg(image: bytes) -> bool:
    return b"<svg" in image[:1024]


def rasterize_svg(svg: bytes) -> bytes:
    """Render an SVG to PNG as Chrome draws it on a dark desktop.

    SVGs are not installed as-is because Qt-based shells ignore CSS inside
    them; ChatGPT's icon gets its only fill from CSS and shows up blank.
    librsvg and CairoSVG apply that CSS but ignore `@media`, so they miss the
    `prefers-color-scheme: dark` variant that Chrome itself would pick.
    """
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir)
        (scratch / "icon.svg").write_bytes(svg)
        wrapper_page = scratch / "icon.html"
        wrapper_page.write_text(SVG_WRAPPER_HTML, encoding="utf-8")
        screenshot = scratch / "icon.png"
        subprocess.run(
            [
                CHROME_COMMAND,
                "--headless",
                "--disable-gpu",
                # Throwaway profile so rendering never touches the real one.
                f"--user-data-dir={scratch / 'profile'}",
                "--force-dark-mode",
                "--force-device-scale-factor=1",
                "--hide-scrollbars",
                "--default-background-color=00000000",
                f"--window-size={ICON_SIZE},{ICON_SIZE}",
                f"--screenshot={screenshot}",
                wrapper_page.as_uri(),
            ],
            capture_output=True,
            check=True,
            timeout=CHROME_RENDER_TIMEOUT_SECONDS,
        )
        return screenshot.read_bytes()


def render_png(image: bytes, output_path: Path) -> None:
    """Resize a raster image into a square icon PNG, padding with transparency."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    geometry = f"{ICON_SIZE}x{ICON_SIZE}"
    subprocess.run(
        [
            "magick", "-", "-resize", geometry,
            "-background", "none", "-gravity", "center", "-extent", geometry,
            # Icons are committed: drop timestamps so regenerating an unchanged
            # icon leaves no git diff.
            "-strip", "-define", "png:exclude-chunks=date,time",
            f"png:{output_path}",
        ],
        input=image,
        check=True,
    )


def read_icon_source(icon_source: str) -> bytes:
    """Read `--icon` as a URL when it has a scheme, otherwise as a local path."""
    if urllib.parse.urlparse(icon_source).scheme:
        return download(icon_source)
    return Path(icon_source).read_bytes()


def add(app: WebApp, icon_source: str | None, files_dir: Path) -> int:
    image = (
        read_icon_source(icon_source) if icon_source else download(discover_manifest_icon_url(app))
    )
    raster_image = rasterize_svg(image) if is_svg(image) else image
    launcher_files = LauncherFiles.under(files_dir, app)
    render_png(raster_image, launcher_files.icon_path)
    launcher_files.desktop_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_files.desktop_path.write_text(render_desktop_entry(app), encoding="utf-8")
    print(launcher_files.desktop_path)
    print(launcher_files.icon_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    commands = parser.add_subparsers(dest="command", required=True)
    add_parser = commands.add_parser("add", help="generate or regenerate one app's launcher")
    add_parser.add_argument("id", help="launcher id, e.g. `chatgpt` for webapp-chatgpt.desktop")
    add_parser.add_argument("name", help='launcher name; by convention the app name plus " Web"')
    add_parser.add_argument("url", help="URL to open as a Chrome app window")
    add_parser.add_argument(
        "--icon", help="SVG or raster icon, as a path or URL; default: the site's manifest icon"
    )
    add_parser.add_argument(
        "--files-dir", type=Path, default=PACKAGE_FILES_DIR, help="package `files/` directory"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return add(WebApp(args.id, args.name, args.url), args.icon, args.files_dir)


if __name__ == "__main__":
    sys.exit(main())

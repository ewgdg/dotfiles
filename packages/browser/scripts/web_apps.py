#!/usr/bin/env python3
"""
web_apps.py - Install Chrome `--app` launchers declared in a TOML spec.

Each app gets `webapp-<id>.desktop` plus PNG icons in the user hicolor theme,
rendered from the committed `icons/<id>.svg` or `icons/<id>.png` next to the
spec. Installing never touches the network: bot-protected sites such as
chatgpt.com and claude.ai reject scripted fetches. Everything named `webapp-*`
belongs to this script; launchers dropped from the spec are removed on apply.

probe: exit 0 when live launchers differ from the spec, 100 when current.
apply: write launchers, render icons, and remove launchers dropped from the spec.
fetch: download one app's icon from its site's manifest, for committing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request


CHROME_COMMAND = "google-chrome-stable"
CHROME_PROFILE_DIRECTORY = "Default"
OWNED_FILE_PREFIX = "webapp-"
# Same sizes Chrome exports to hicolor when it installs a web app.
ICON_SIZES = (16, 32, 48, 128, 256)
ICON_SOURCE_SUFFIXES = (".svg", ".png")
# Recorded in the launcher so an edited icon source shows up as a change.
ICON_DIGEST_KEY = "X-WebApp-Icon-Digest"
SVG_RENDER_SIZE = max(ICON_SIZES)
# Fetched raster icons are shrunk to the largest installed size before committing.
FETCHED_RASTER_MAX_SIZE = max(ICON_SIZES)
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
PROBE_ACTION_NEEDED = 0
PROBE_NOOP = 100


@dataclass(frozen=True)
class WebApp:
    id: str
    name: str
    url: str


@dataclass(frozen=True)
class InstallLayout:
    applications_dir: Path
    hicolor_dir: Path

    @classmethod
    def from_environment(cls) -> InstallLayout:
        data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
        return cls(data_home / "applications", data_home / "icons/hicolor")

    def desktop_path(self, app: WebApp) -> Path:
        return self.applications_dir / f"{OWNED_FILE_PREFIX}{app.id}.desktop"

    def icon_paths(self, app: WebApp) -> dict[int, Path]:
        return {
            size: self.hicolor_dir / f"{size}x{size}/apps/{OWNED_FILE_PREFIX}{app.id}.png"
            for size in ICON_SIZES
        }

    def expected_files(self, apps: list[WebApp]) -> set[Path]:
        return {
            path
            for app in apps
            for path in (self.desktop_path(app), *self.icon_paths(app).values())
        }

    def owned_files(self) -> set[Path]:
        return {
            *self.applications_dir.glob(f"{OWNED_FILE_PREFIX}*.desktop"),
            *self.hicolor_dir.glob(f"*/apps/{OWNED_FILE_PREFIX}*.png"),
        }


def load_web_apps(spec_path: Path) -> list[WebApp]:
    spec = tomllib.loads(spec_path.read_text(encoding="utf-8"))
    return [WebApp(**app) for app in spec["apps"]]


def icons_dir_for(spec_path: Path) -> Path:
    return spec_path.parent / "icons"


def icon_source_path(icons_dir: Path, app: WebApp) -> Path:
    candidates = [icons_dir / f"{app.id}{suffix}" for suffix in ICON_SOURCE_SUFFIXES]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) != 1:
        names = " or ".join(path.name for path in candidates)
        raise RuntimeError(
            f"{app.id}: expected exactly one icon source ({names}) in {icons_dir}; "
            f"run `fetch` or add one"
        )
    return existing[0]


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


def render_desktop_entry(app: WebApp, icon_source: Path) -> str:
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
            f"Icon={OWNED_FILE_PREFIX}{app.id}",
            f"StartupWMClass={chrome_app_window_class(app.url)}",
            "Terminal=false",
            "StartupNotify=true",
            "Categories=Network;",
            f"{ICON_DIGEST_KEY}={hashlib.sha256(icon_source.read_bytes()).hexdigest()}",
            "",
        ]
    )


def launcher_is_current(layout: InstallLayout, app: WebApp, icon_source: Path) -> bool:
    desktop_path = layout.desktop_path(app)
    return (
        desktop_path.is_file()
        and desktop_path.read_text(encoding="utf-8") == render_desktop_entry(app, icon_source)
        and all(path.is_file() for path in layout.icon_paths(app).values())
    )


def stale_files(layout: InstallLayout, apps: list[WebApp]) -> set[Path]:
    return layout.owned_files() - layout.expected_files(apps)


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
                f"--window-size={SVG_RENDER_SIZE},{SVG_RENDER_SIZE}",
                f"--screenshot={screenshot}",
                wrapper_page.as_uri(),
            ],
            capture_output=True,
            check=True,
            timeout=CHROME_RENDER_TIMEOUT_SECONDS,
        )
        return screenshot.read_bytes()


def render_png(image: bytes, size: int, output_path: Path) -> None:
    """Resize a raster image into a square PNG, padding with transparency."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    geometry = f"{size}x{size}"
    subprocess.run(
        [
            "magick", "-", "-resize", geometry,
            "-background", "none", "-gravity", "center", "-extent", geometry,
            f"png:{output_path}",
        ],
        input=image,
        check=True,
    )


def install_launcher(layout: InstallLayout, app: WebApp, icon_source: Path) -> None:
    image = icon_source.read_bytes()
    raster_image = rasterize_svg(image) if is_svg(image) else image
    for size, icon_path in layout.icon_paths(app).items():
        render_png(raster_image, size, icon_path)
    # Written last so a failed icon render leaves the launcher out of date.
    layout.applications_dir.mkdir(parents=True, exist_ok=True)
    layout.desktop_path(app).write_text(render_desktop_entry(app, icon_source), encoding="utf-8")


def probe(layout: InstallLayout, apps: list[WebApp], icons_dir: Path) -> int:
    is_current = all(
        launcher_is_current(layout, app, icon_source_path(icons_dir, app)) for app in apps
    ) and not stale_files(layout, apps)
    return PROBE_NOOP if is_current else PROBE_ACTION_NEEDED


def apply(layout: InstallLayout, apps: list[WebApp], icons_dir: Path) -> int:
    for app in apps:
        icon_source = icon_source_path(icons_dir, app)
        if not launcher_is_current(layout, app, icon_source):
            install_launcher(layout, app, icon_source)
    for path in stale_files(layout, apps):
        path.unlink()
    return 0


def fetch(apps: list[WebApp], icons_dir: Path, app_id: str) -> int:
    """Save an app's icon as its committed source: SVG as-is, rasters shrunk."""
    app = next(app for app in apps if app.id == app_id)
    image = download(discover_manifest_icon_url(app))
    icons_dir.mkdir(exist_ok=True)
    suffix = ".svg" if is_svg(image) else ".png"
    saved_path = icons_dir / f"{app.id}{suffix}"
    if suffix == ".svg":
        saved_path.write_bytes(image)
    else:
        max_geometry = f"{FETCHED_RASTER_MAX_SIZE}x{FETCHED_RASTER_MAX_SIZE}>"
        subprocess.run(["magick", "-", "-resize", max_geometry, f"png:{saved_path}"], input=image, check=True)
    for other_suffix in set(ICON_SOURCE_SUFFIXES) - {suffix}:
        (icons_dir / f"{app.id}{other_suffix}").unlink(missing_ok=True)
    print(saved_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("probe", "apply"):
        commands.add_parser(command).add_argument("spec", type=Path, help="TOML spec listing [[apps]]")
    fetch_parser = commands.add_parser("fetch")
    fetch_parser.add_argument("spec", type=Path, help="TOML spec listing [[apps]]")
    fetch_parser.add_argument("app_id", help="`id` of the app whose icon to download")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    apps = load_web_apps(args.spec)
    icons_dir = icons_dir_for(args.spec)
    if args.command == "fetch":
        return fetch(apps, icons_dir, args.app_id)
    commands = {"probe": probe, "apply": apply}
    return commands[args.command](InstallLayout.from_environment(), apps, icons_dir)


if __name__ == "__main__":
    sys.exit(main())

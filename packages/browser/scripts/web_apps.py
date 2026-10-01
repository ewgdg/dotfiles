#!/usr/bin/env python3
"""
web_apps.py - Install Chrome `--app` launchers declared in a TOML spec.

Each app gets `webapp-<id>.desktop` plus PNG icons in the user hicolor theme.
Everything named `webapp-*` belongs to this script; launchers dropped from the
spec are removed on apply.

probe: exit 0 when live launchers differ from the spec, 100 when current.
apply: write launchers, render icons, and remove launchers dropped from the spec.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
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
# Tells web-app launchers apart from native apps of the same name.
DISPLAY_NAME_SUFFIX = " Web"
# Same sizes Chrome exports to hicolor when it installs a web app.
ICON_SIZES = (16, 32, 48, 128, 256)
ICON_SOURCE_KEY = "X-WebApp-Icon-Source"
SVG_RENDER_SIZE = max(ICON_SIZES)
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
    icon: str


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
            f"Name={app.name}{DISPLAY_NAME_SUFFIX}",
            f"Exec={exec_command}",
            f"Icon={OWNED_FILE_PREFIX}{app.id}",
            f"StartupWMClass={chrome_app_window_class(app.url)}",
            "Terminal=false",
            "StartupNotify=true",
            "Categories=Network;",
            # Recorded so a changed icon URL shows up as a launcher change.
            f"{ICON_SOURCE_KEY}={app.icon}",
            "",
        ]
    )


def launcher_is_current(layout: InstallLayout, app: WebApp) -> bool:
    desktop_path = layout.desktop_path(app)
    return (
        desktop_path.is_file()
        and desktop_path.read_text(encoding="utf-8") == render_desktop_entry(app)
        and all(path.is_file() for path in layout.icon_paths(app).values())
    )


def stale_files(layout: InstallLayout, apps: list[WebApp]) -> set[Path]:
    return layout.owned_files() - layout.expected_files(apps)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read()


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


def install_launcher(layout: InstallLayout, app: WebApp) -> None:
    image = download(app.icon)
    raster_image = rasterize_svg(image) if is_svg(image) else image
    for size, icon_path in layout.icon_paths(app).items():
        render_png(raster_image, size, icon_path)
    # Written last so a failed icon render leaves the launcher out of date.
    layout.applications_dir.mkdir(parents=True, exist_ok=True)
    layout.desktop_path(app).write_text(render_desktop_entry(app), encoding="utf-8")


def probe(layout: InstallLayout, apps: list[WebApp]) -> int:
    is_current = all(launcher_is_current(layout, app) for app in apps) and not stale_files(
        layout, apps
    )
    return PROBE_NOOP if is_current else PROBE_ACTION_NEEDED


def apply(layout: InstallLayout, apps: list[WebApp]) -> int:
    for app in apps:
        if not launcher_is_current(layout, app):
            install_launcher(layout, app)
    for path in stale_files(layout, apps):
        path.unlink()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("command", choices=["probe", "apply"])
    parser.add_argument("spec", type=Path, help="TOML spec listing [[apps]]")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    commands = {"probe": probe, "apply": apply}
    return commands[args.command](InstallLayout.from_environment(), load_web_apps(args.spec))


if __name__ == "__main__":
    sys.exit(main())

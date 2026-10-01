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
# Same sizes Chrome exports to hicolor when it installs a web app.
ICON_SIZES = (16, 32, 48, 128, 256)
ICON_SOURCE_KEY = "X-WebApp-Icon-Source"
ICON_FILL_KEY = "X-WebApp-Icon-Fill"
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
    # Overrides the fill of a single-colour SVG, e.g. to pick its dark variant.
    icon_fill: str | None = None


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
            f"Name={app.name}",
            f"Exec={exec_command}",
            f"Icon={OWNED_FILE_PREFIX}{app.id}",
            f"StartupWMClass={chrome_app_window_class(app.url)}",
            "Terminal=false",
            "StartupNotify=true",
            "Categories=Network;",
            # Recorded so changed icon settings show up as a launcher change.
            f"{ICON_SOURCE_KEY}={app.icon}",
            *([f"{ICON_FILL_KEY}={app.icon_fill}"] if app.icon_fill else []),
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


def render_png(image: bytes, size: int, output_path: Path, fill_stylesheet: Path | None) -> None:
    """Rasterize into a square PNG.

    Site SVGs are rasterized instead of installed because Qt-based shells
    ignore CSS inside SVGs; ChatGPT's icon gets its only fill from CSS and
    shows up blank. librsvg applies that CSS.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if is_svg(image):
        command = ["rsvg-convert", "-w", str(size), "-h", str(size), "-a", "-o", str(output_path)]
        if fill_stylesheet:
            command += ["--stylesheet", str(fill_stylesheet)]
    else:
        geometry = f"{size}x{size}"
        command = [
            "magick", "-", "-resize", geometry,
            "-background", "none", "-gravity", "center", "-extent", geometry,
            f"png:{output_path}",
        ]
    subprocess.run(command, input=image, check=True)


def install_launcher(layout: InstallLayout, app: WebApp) -> None:
    image = download(app.icon)
    if app.icon_fill and not is_svg(image):
        raise ValueError(f"{app.id}: icon_fill needs an SVG icon")
    with tempfile.TemporaryDirectory() as scratch_dir:
        fill_stylesheet = None
        if app.icon_fill:
            fill_stylesheet = Path(scratch_dir, "fill.css")
            # `!important` because user stylesheets lose to the SVG's own CSS;
            # librsvg ignores `@media`, so dark-mode rules never apply otherwise.
            fill_stylesheet.write_text(f"svg {{ fill: {app.icon_fill} !important; }}\n")
        for size, icon_path in layout.icon_paths(app).items():
            render_png(image, size, icon_path, fill_stylesheet)
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

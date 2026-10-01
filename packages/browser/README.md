# browser

Chromium/Electron launch flags, plus Chrome web-app launchers.

## Web apps

`web-apps.toml` lists sites to open as Chrome `--app` windows. The `web_apps_installed` probe target runs `scripts/web_apps.py`, which installs for each app:

- `~/.local/share/applications/webapp-<id>.desktop`
- PNG icons at `~/.local/share/icons/hicolor/<size>x<size>/apps/webapp-<id>.png`, sizes 16/32/48/128/256

Everything named `webapp-*` belongs to the script. Removing an app from the spec deletes its launcher and icons on the next push.

Add an app with `id`, `name`, `url`, and `icon`. Launcher names get a ` Web` suffix, e.g. `Gemini Web`, to tell them apart from native apps. `icon` must be a direct image URL; site pages often block scraping, so the script does not discover icons.

### Why not Chrome's "Install app"

Chrome has no supported CLI for installing a web app into a personal profile, so those launchers cannot be tracked. `--app=<url>` launchers can.

### Icons are rendered to PNG, never installed as SVG

The desktop shell draws launcher icons, not Chrome. Qt-based shells such as Noctalia ignore CSS inside SVGs. ChatGPT's favicon gets its only fill from CSS, so installed as-is it shows blank. Chrome itself exports PNGs only.

The script renders SVGs with headless Chrome in dark mode, through a wrapper page that scales the SVG to the window, then resizes with `magick`. Raster icons go straight to `magick`. Chrome is used because standalone converters (librsvg, CairoSVG) apply the CSS but ignore `@media`, so icons with a `prefers-color-scheme: dark` variant come out in their light colours; ChatGPT's black logo nearly disappears on a dark launcher.

### Match windows by app-id, not title

An `--app=<url>` window takes the page's live title, so title-based window rules break. The stable handle is the app-id Chrome derives from the URL, written to the launcher's `StartupWMClass`: `chrome-<host>_<path with / as _>-Default`, e.g. `chrome-chatgpt.com__-Default`.

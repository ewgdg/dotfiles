# browser

Chromium/Electron launch flags, plus Chrome web-app launchers.

## Web apps

`web-apps.toml` lists sites to open as Chrome `--app` windows, and `icons/` holds one committed icon per app: `<id>.svg`, or `<id>.png` when the site has no SVG. The `web_apps_installed` probe target runs `scripts/web_apps.py`, which installs for each app:

- `~/.local/share/applications/webapp-<id>.desktop`
- PNG icons at `~/.local/share/icons/hicolor/<size>x<size>/apps/webapp-<id>.png`, sizes 16/32/48/128/256

Everything named `webapp-*` belongs to the script. Removing an app from the spec deletes its launcher and icons on the next push. Editing an icon in `icons/` re-renders it.

### Adding an app

1. Add `id`, `name`, and `url` to `web-apps.toml`. By convention `name` is the app's own name plus ` Web`, e.g. `Gemini Web`, to tell launchers apart from native apps.
2. Run `uv run packages/browser/scripts/web_apps.py fetch packages/browser/web-apps.toml <id>` and commit the saved icon.

`fetch` reads the site's web app manifest (`<link rel="manifest">`) and picks an icon like Chrome: SVG first, then the largest size, skipping maskable-only icons. SVGs are saved as-is; raster icons are shrunk to 256px. When the page blocks scripted fetches (chatgpt.com and claude.ai return a Cloudflare 403) or has no manifest, save the site's icon into `icons/` by hand; prefer its SVG favicon.

### Install is offline

Pushing never fetches icons: bot protection on sites like ChatGPT and Claude changes without notice, and even direct icon URLs on the same site were blocked inconsistently. Committed sources make installs deterministic.

### Why not Chrome's "Install app"

Chrome has no supported CLI for installing a web app into a personal profile, so those launchers cannot be tracked. `--app=<url>` launchers can.

### Icons are rendered to PNG, never installed as SVG

The desktop shell draws launcher icons, not Chrome. Qt-based shells such as Noctalia ignore CSS inside SVGs. ChatGPT's favicon gets its only fill from CSS, so installed as-is it shows blank. Chrome itself exports PNGs only.

The script renders SVGs with headless Chrome in dark mode, through a wrapper page that scales the SVG to the window, then resizes with `magick`. Raster icons go straight to `magick`. Chrome is used because standalone converters (librsvg, CairoSVG) apply the CSS but ignore `@media`, so icons with a `prefers-color-scheme: dark` variant come out in their light colours; ChatGPT's black logo nearly disappears on a dark launcher.

### Match windows by app-id, not title

An `--app=<url>` window takes the page's live title, so title-based window rules break. The stable handle is the app-id Chrome derives from the URL, written to the launcher's `StartupWMClass`: `chrome-<host>_<path with / as _>-Default`, e.g. `chrome-chatgpt.com__-Default`.

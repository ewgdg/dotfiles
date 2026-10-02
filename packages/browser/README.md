# browser

Chromium/Electron launch flags, plus Chrome web-app launchers.

## Web apps

Each web app is a Chrome `--app` launcher, committed as two generated files that dotman tracks:

- `files/local/share/applications/webapp-<id>.desktop`
- `files/local/share/icons/hicolor/256x256/apps/webapp-<id>.png`

The live directories are shared with other apps, so both targets ignore everything except `webapp-*`. Deleting an app's two files from the repo removes it live on the next push.

### Adding an app

```sh
uv run packages/browser/scripts/web_apps.py add <id> "<Name> Web" <url> [--icon <svg-or-png>]
```

- By convention the name is the app's own name plus ` Web`, e.g. `Gemini Web`, to tell launchers apart from native apps.
- Without `--icon`, the script reads the site's web app manifest (`<link rel="manifest">`) and picks an icon like Chrome: SVG first, then the largest size, skipping maskable-only icons.
- Pass `--icon` when the site blocks scripted fetches (chatgpt.com and claude.ai return a Cloudflare 403) or has no manifest; prefer the site's SVG favicon.
- When the site has no usable icon (Gmail and Outlook show their manifests only after sign-in), take one from [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) (browse at [dashboardicons.com](https://dashboardicons.com)). Names do not always match the app (`gmail`, but `microsoft-outlook`), so look the name up rather than guessing it. Each icon is served at `https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/<name>.svg`; download it and pass the file to `--icon`.
- Re-run `add` to change an app's name, URL or icon. Unchanged inputs regenerate byte-identical files.

### One icon size

Only a 256px PNG is generated. Icon themes fall back to the nearest available size and the shell scales it, so smaller sizes would only be the same image resized ahead of time.

### Why not Chrome's "Install app"

Chrome has no supported CLI for installing a web app into a personal profile, so those launchers cannot be tracked. `--app=<url>` launchers can.

### Icons are rendered to PNG, never committed as SVG

The desktop shell draws launcher icons, not Chrome. Qt-based shells such as Noctalia ignore CSS inside SVGs. ChatGPT's favicon gets its only fill from CSS, so installed as-is it shows blank. Chrome itself exports PNGs only.

`add` renders SVGs with headless Chrome in dark mode, through a wrapper page that scales the SVG to the window, then resizes with `magick`. Raster icons go straight to `magick`. Chrome is used because standalone converters (librsvg, CairoSVG) apply the CSS but ignore `@media`, so icons with a `prefers-color-scheme: dark` variant come out in their light colours; ChatGPT's black logo nearly disappears on a dark launcher.

### Match windows by app-id, not title

An `--app=<url>` window takes the page's live title, so title-based window rules break. The stable handle is the app-id Chrome derives from the URL, written to the launcher's `StartupWMClass`: `chrome-<host>_<path with / as _>-Default`, e.g. `chrome-chatgpt.com__-Default`.

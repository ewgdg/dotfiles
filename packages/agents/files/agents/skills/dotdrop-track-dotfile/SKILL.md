---
name: dotdrop-track-dotfile
description: Track a new dotfile, config file, or config directory in the user's dotdrop-managed repo. Use when Codex needs to add a file under ~/.config, ~/.local, ~/.codex, ~/.agents, ~/bin, or similar by finding the repo from DOTDROP_CONFIG first, adding a key and profile entry in config.yaml, and copying the live file or directory into dotfiles/.
---

# Dotdrop Track Dotfile

Use this skill to add a live file or directory into a dotdrop repo.

## Steps

1. Find the repo root.
2. Edit `config.yaml`.
3. Copy the live file or directory into `dotfiles/`.
4. Verify the mapping.

## 1. Find The Repo Root

- First read `DOTDROP_CONFIG`.
- If it is set, use its parent directory as the repo root.
- If it is not set, fall back to `/home/xian/projects/dotfiles`.
- Read `<repo>/AGENTS.md` before editing repo files.

Useful commands:

```bash
rtk sh -lc 'printf "%s\n" "${DOTDROP_CONFIG:-}"'
rtk sh -lc 'repo_root=$(dirname "${DOTDROP_CONFIG:-/home/xian/projects/dotfiles/config.yaml}") && printf "%s\n" "$repo_root"'
```

## 2. Edit config.yaml

In `<repo>/config.yaml`:

- Add a new key under `dotfiles:`.
- Use `f_...` for files and `d_...` for directories.
- Set `src` under `dotfiles/`.
- Set `dst` to the live path.
- Add only the metadata the entry actually needs.
- Add the key to the relevant profile, or it will not be deployed.
- Follow existing repo conventions when naming keys and structuring entries.

Example:

```yaml
f_codex_AGENTS_override_md:
  src: codex/AGENTS.override.md
  dst: ~/.codex/AGENTS.override.md
```

Only add extra fields when needed, such as:

- `chmod`
- `actions`
- `trans_update` / `trans_install`
- `cmpignore` / `upignore` / `instignore`

## 3. Copy The Live File

- If the live file or directory already exists, copy it into `<repo>/dotfiles/...`.
- If nothing exists yet, create the repo source directly.
- Keep the repo path aligned with the destination path shape when practical.

Examples:

- `~/.codex/AGENTS.override.md` -> `<repo>/dotfiles/codex/AGENTS.override.md`
- `~/.config/alacritty/alacritty.toml` -> `<repo>/dotfiles/config/alacritty/alacritty.toml`
- `~/.local/share/applications/foo.desktop` -> `<repo>/dotfiles/local/share/applications/foo.desktop`

## 4. Verify

- Validate that `config.yaml` parses.
- Check that the key is included in the intended profile.
- Optionally run `dotdrop compare -p <profile>` if deployment verification is needed.
- Review `git status`.

Useful commands:

```bash
rtk sh -lc 'repo_root=$(dirname "${DOTDROP_CONFIG:-/home/xian/projects/dotfiles/config.yaml}") && cd "$repo_root" && uv run python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path(\"config.yaml\").read_text()); print(\"config.yaml OK\")"'
rtk sh -lc 'repo_root=$(dirname "${DOTDROP_CONFIG:-/home/xian/projects/dotfiles/config.yaml}") && cd "$repo_root" && dotdrop files -p <profile> --grepable | rg "<key>"'
rtk sh -lc 'repo_root=$(dirname "${DOTDROP_CONFIG:-/home/xian/projects/dotfiles/config.yaml}") && cd "$repo_root" && git status --short'
```

## Completion Checklist

- Repo root found
- Key added to `config.yaml`
- Key added to the relevant profile
- Live file or directory copied into `dotfiles/`
- `config.yaml` parses cleanly

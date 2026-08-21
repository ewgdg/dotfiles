# DeepSeek Harness

This package tracks the non-secret model and provider configuration in `~/.dsh/settings.yaml`. It also maintains the user-global instruction link `~/.dsh/AGENTS.md` as a symlink to `~/.agents/AGENTS.md` (the shared agents file), matching the Codex CLI setup.

On Linux, `linux/deepseek-harness` installs the `dsh` command, application-menu entry, icon, and desktop identity. Install DeepSeek Harness once with `npm install -g @deepseek-ai/dsh`. Both launch paths then run that installed release, wait for the Web UI, and open it in a dedicated native-Wayland Chrome window with translation prompts disabled. Terminal mode runs until `Ctrl+C`; the terminal-free application-menu mode stops DSH when its Chrome window closes. DSH is single-instance: another launch asks Chrome to focus the existing DSH tab instead of starting another server, tab, or window. Chrome keeps its live-local app profile under `${XDG_STATE_HOME:-~/.local/state}/deepseek-harness/chrome`, and application-mode server output goes to `dsh.log` beside that profile. No manual Chrome web-app installation is required.

Configure providers through **Settings → Models** in the Web UI, then pull this package to capture the resulting settings. The onboarding acknowledgement, default model choice, agent preset, and permission preset stay live-local on each host.

Credentials remain live-local in `~/.dsh/.credentials.yaml` and must not be added to this package. Keep authentication values out of custom provider `headers`; use credential references managed by DSH instead.

Generated profiles, sessions, storage, caches, and runtime files under `~/.dsh` are intentionally unmanaged.

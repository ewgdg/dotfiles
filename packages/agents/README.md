# agents

Shared agent home (`~/.agents`): instructions, docs, and skills.

## Skills

- **Custom skills** are tracked as files under `files/agents/skills/`.
- **`npx skills`-managed skills** are tracked only by the lock file `files/local/state/skills/.skill-lock.json`. Their folders stay live-only:
  - `d_agents` excludes them through `ignore.command`, using the union of the repo and live locks. Pull skips new installs; push leaves installed folders alone.
  - `managed_skills_installed` probes for skills in the repo lock that are missing live, and reinstalls them with `npx skills add` for the lock's `lastSelectedAgents`: the agents last picked in the `npx skills` menu, synced so every machine's menu defaults to them. Universal agents read `~/.agents/skills` without being listed. Its relative agent links coexist with `claude_skills_link`, which compares links by where they point.
  - The lock target keeps `skillFolderHash`, `installedAt`, and `updatedAt` live-only. They are per-install metadata, `npx skills add` does not pin to them, and `npx skills update` needs the live hash to match the live folder.

Workflow: install or remove with `npx skills ... -g`, then `dotman pull` to record the lock. Pull before push, or push drops lock entries added since the last pull.

Helper: `scripts/managed_skills.mjs` (`ignores | probe | install`).

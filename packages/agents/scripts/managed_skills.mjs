#!/usr/bin/env node
// Skills installed by `npx skills` are tracked only through their lock file.
// Their folders under ~/.agents/skills stay live-only; this helper derives
// d_agents exclusions from the lock and reinstalls folders the repo lock lists.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PROBE_ACTION_NEEDED = 0;
const PROBE_NOOP = 100;

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoLockPath = join(packageRoot, "files/local/state/skills/.skill-lock.json");
const liveLockPath = join(homedir(), ".local/state/skills/.skill-lock.json");
const liveSkillsDir = join(homedir(), ".agents/skills");

const readLock = (path) => JSON.parse(readFileSync(path, "utf8"));

// The live lock is absent on a fresh machine until the lock target is pushed.
const readLiveLockIfPresent = () => (existsSync(liveLockPath) ? readLock(liveLockPath) : { skills: {} });

const isInstalled = (name) => existsSync(join(liveSkillsDir, name, "SKILL.md"));

const missingSkills = (lock) =>
  Object.entries(lock.skills).filter(([name]) => !isInstalled(name));

// Union of both locks: pull must skip skills installed live but not yet in the
// repo lock, and push must skip skills the repo lock lists but live lacks.
function printIgnores() {
  const names = new Set([
    ...Object.keys(readLock(repoLockPath).skills),
    ...Object.keys(readLiveLockIfPresent().skills),
  ]);
  for (const name of [...names].sort()) console.log(`/skills/${name}/`);
}

function probe() {
  const missing = missingSkills(readLock(repoLockPath));
  for (const [name] of missing) console.error(`managed skill missing: ${name}`);
  process.exit(missing.length > 0 ? PROBE_ACTION_NEEDED : PROBE_NOOP);
}

function install(agents) {
  if (agents.length === 0) throw new Error("install needs at least one agent");
  for (const [name, entry] of missingSkills(readLock(repoLockPath))) {
    const result = spawnSync(
      "npx",
      ["-y", "skills", "add", entry.sourceUrl, "--global", "--skill", name, "--yes", "--agent", ...agents],
      { stdio: "inherit" },
    );
    if (result.status !== 0) throw new Error(`failed to install managed skill: ${name}`);
  }
}

const commands = { ignores: printIgnores, probe, install };
const command = commands[process.argv[2]];
if (!command) {
  console.error("usage: managed_skills.mjs ignores | probe | install AGENT...");
  process.exit(2);
}
command(process.argv.slice(3));

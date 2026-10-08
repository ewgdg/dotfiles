#!/usr/bin/env node
// Skills installed by `npx skills` are tracked only through their lock file.
// Their folders under ~/.agents/skills stay live-only; this helper derives
// d_agents exclusions from the lock and reconciles installed folders with the
// repo: it installs skills the repo lock lists and removes skills the repo owns
// neither through its lock nor as a repo-authored skill.
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PROBE_ACTION_NEEDED = 0;
const PROBE_NOOP = 100;

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoLockPath = join(packageRoot, "files/local/state/skills/.skill-lock.json");
const liveLockPath = join(homedir(), ".local/state/skills/.skill-lock.json");
const liveSkillsDir = join(homedir(), ".agents/skills");
const repoAuthoredSkillsDir = join(packageRoot, "files/agents/skills");

const readLock = (path) => JSON.parse(readFileSync(path, "utf8"));

// The live lock is absent on a fresh machine until the lock target is pushed.
const readLiveLockIfPresent = () => (existsSync(liveLockPath) ? readLock(liveLockPath) : { skills: {} });

const isInstalled = (name) => existsSync(join(liveSkillsDir, name, "SKILL.md"));

const missingSkills = (lock) =>
  Object.entries(lock.skills).filter(([name]) => !isInstalled(name));

// Mirrors how `npx skills remove` discovers skills, so every orphan found here
// is one it can remove.
const skillNamesIn = (dir) =>
  existsSync(dir)
    ? readdirSync(dir, { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && !entry.name.startsWith(".") && existsSync(join(dir, entry.name, "SKILL.md")))
        .map((entry) => entry.name)
    : [];

// Push means the repo wins. Sync runs this in its push step after capturing
// live lock changes, so skills installed live since the last pull are kept.
function orphanedSkills(lock) {
  const ownedNames = new Set([...Object.keys(lock.skills), ...skillNamesIn(repoAuthoredSkillsDir)]);
  return skillNamesIn(liveSkillsDir).filter((name) => !ownedNames.has(name)).sort();
}

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
  const lock = readLock(repoLockPath);
  const missing = missingSkills(lock);
  const orphaned = orphanedSkills(lock);
  for (const [name] of missing) console.error(`managed skill missing: ${name}`);
  for (const name of orphaned) console.error(`managed skill orphaned: ${name}`);
  process.exit(missing.length > 0 || orphaned.length > 0 ? PROBE_ACTION_NEEDED : PROBE_NOOP);
}

function install(lock) {
  // `npx skills` saves the agents picked in its interactive menu here; `--yes`
  // never reads it, and without `--agent` it falls back to every known agent
  // when none are detected yet, as on a fresh machine.
  const agents = lock.lastSelectedAgents ?? [];
  if (agents.length === 0) throw new Error(`lastSelectedAgents is empty in ${repoLockPath}`);
  for (const [name, entry] of missingSkills(lock)) {
    const result = spawnSync(
      "npx",
      ["-y", "skills", "add", entry.sourceUrl, "--global", "--skill", name, "--yes", "--agent", ...agents],
      { stdio: "inherit" },
    );
    if (result.status !== 0) throw new Error(`failed to install managed skill: ${name}`);
  }
}

// Without `--agent`, `npx skills remove` also deletes the skill's links in
// every agent's global skills folder.
function removeOrphans(lock) {
  const orphaned = orphanedSkills(lock);
  if (orphaned.length === 0) return;
  const result = spawnSync("npx", ["-y", "skills", "remove", "--global", "--yes", ...orphaned], { stdio: "inherit" });
  if (result.status !== 0) throw new Error(`failed to remove orphaned skills: ${orphaned.join(", ")}`);
  // `npx skills remove` exits 0 when it matches nothing or only warns on failed deletes.
  const remaining = orphaned.filter(isInstalled);
  if (remaining.length > 0) throw new Error(`orphaned skills still installed: ${remaining.join(", ")}`);
}

function reconcile() {
  const lock = readLock(repoLockPath);
  install(lock);
  removeOrphans(lock);
}

const commands = { ignores: printIgnores, probe, reconcile };
const command = commands[process.argv[2]];
if (!command) {
  console.error("usage: managed_skills.mjs ignores | probe | reconcile");
  process.exit(2);
}
command();

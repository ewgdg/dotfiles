import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const PROBE_ACTION_NEEDED = 0;
const PROBE_NOOP = 100;

const scriptSourcePath = join(dirname(fileURLToPath(import.meta.url)), "..", "scripts", "managed_skills.mjs");

// Records each `npx` call and mimics `skills remove --global` by deleting the
// named folders, so tests observe the live tree rather than the command line.
const FAKE_NPX = `#!/bin/sh
printf '%s\\n' "$*" >> "$NPX_CALLS_LOG"
[ "$FAKE_NPX_IGNORES_REMOVE" = 1 ] && exit 0
shift 3
for arg in "$@"; do
  case "$arg" in --*) ;; *) rm -rf "$HOME/.agents/skills/$arg" ;; esac
done
`;

function writeSkill(skillsDir, name) {
  mkdirSync(join(skillsDir, name), { recursive: true });
  writeFileSync(join(skillsDir, name, "SKILL.md"), `# ${name}\n`);
}

// Lays out a package copy with its own repo lock and repo-authored skills, a
// fake HOME with installed skills, and a fake `npx` on PATH.
function createFixture(t, { repoLockSkills, repoAuthoredSkills, installedSkills }) {
  const root = mkdtempSync(join(tmpdir(), "managed-skills-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));

  const packageRoot = join(root, "package");
  const scriptPath = join(packageRoot, "scripts", "managed_skills.mjs");
  mkdirSync(dirname(scriptPath), { recursive: true });
  copyFileSync(scriptSourcePath, scriptPath);

  const repoLockPath = join(packageRoot, "files/local/state/skills/.skill-lock.json");
  mkdirSync(dirname(repoLockPath), { recursive: true });
  const lockEntries = repoLockSkills.map((name) => [name, { sourceUrl: `https://example.invalid/${name}.git` }]);
  writeFileSync(repoLockPath, JSON.stringify({ skills: Object.fromEntries(lockEntries), lastSelectedAgents: ["claude-code"] }));

  for (const name of repoAuthoredSkills) writeSkill(join(packageRoot, "files/agents/skills"), name);

  const home = join(root, "home");
  const liveSkillsDir = join(home, ".agents/skills");
  for (const name of installedSkills) writeSkill(liveSkillsDir, name);

  const binDir = join(root, "bin");
  mkdirSync(binDir);
  writeFileSync(join(binDir, "npx"), FAKE_NPX);
  chmodSync(join(binDir, "npx"), 0o755);

  const npxCallsLog = join(root, "npx-calls.log");
  const run = (command, extraEnv = {}) =>
    spawnSync(process.execPath, [scriptPath, command], {
      encoding: "utf8",
      env: { ...process.env, HOME: home, PATH: `${binDir}:${process.env.PATH}`, NPX_CALLS_LOG: npxCallsLog, ...extraEnv },
    });
  const npxCalls = () => (existsSync(npxCallsLog) ? readFileSync(npxCallsLog, "utf8").trim().split("\n") : []);
  const isInstalled = (name) => existsSync(join(liveSkillsDir, name, "SKILL.md"));
  return { run, npxCalls, isInstalled };
}

test("probe asks for work when an installed skill is owned by neither the repo lock nor the repo", (t) => {
  const fixture = createFixture(t, {
    repoLockSkills: ["locked"],
    repoAuthoredSkills: ["authored"],
    installedSkills: ["locked", "authored", "orphan"],
  });
  assert.equal(fixture.run("probe").status, PROBE_ACTION_NEEDED);
});

test("probe is a noop when every installed skill is owned and none is missing", (t) => {
  const fixture = createFixture(t, {
    repoLockSkills: ["locked"],
    repoAuthoredSkills: ["authored"],
    installedSkills: ["locked", "authored"],
  });
  assert.equal(fixture.run("probe").status, PROBE_NOOP);
});

test("reconcile removes orphaned skills through npx skills and keeps owned ones", (t) => {
  const fixture = createFixture(t, {
    repoLockSkills: ["locked"],
    repoAuthoredSkills: ["authored"],
    installedSkills: ["locked", "authored", "orphan-a", "orphan-b"],
  });
  const result = fixture.run("reconcile");
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(fixture.npxCalls(), ["-y skills remove --global --yes orphan-a orphan-b"]);
  assert.deepEqual(
    ["locked", "authored", "orphan-a", "orphan-b"].map(fixture.isInstalled),
    [true, true, false, false],
  );
});

test("reconcile fails when npx skills leaves an orphan in place", (t) => {
  const fixture = createFixture(t, {
    repoLockSkills: [],
    repoAuthoredSkills: [],
    installedSkills: ["orphan"],
  });
  const result = fixture.run("reconcile", { FAKE_NPX_IGNORES_REMOVE: "1" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /orphaned skills still installed: orphan/);
});

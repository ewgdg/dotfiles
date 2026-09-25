'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const subagentStatuslinePath = path.join(__dirname, '..', 'files', 'claude', 'subagent-statusline.js');
const COLORS = Object.freeze({ cyan: '\x1b[96m', green: '\x1b[92m', yellow: '\x1b[93m', blue: '\x1b[94m', red: '\x1b[91m', reset: '\x1b[0m' });

function stripAnsi(value) {
  return value.replace(/\x1b\[[0-9;]*m/g, '');
}

// Mirrors Claude Code's layout: <session>.jsonl plus <session>/subagents/agent-<id>.meta.json.
function createSession(t, agentTypes = {}) {
  const projectDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-subagent-statusline-'));
  t.after(() => fs.rmSync(projectDirectory, { recursive: true, force: true }));
  const subagentsDirectory = path.join(projectDirectory, 'session', 'subagents');
  fs.mkdirSync(subagentsDirectory, { recursive: true });
  for (const [taskId, agentType] of Object.entries(agentTypes)) {
    fs.writeFileSync(path.join(subagentsDirectory, `agent-${taskId}.meta.json`), JSON.stringify({ agentType }));
  }
  const transcriptPath = path.join(projectDirectory, 'session.jsonl');
  fs.writeFileSync(transcriptPath, '');
  return transcriptPath;
}

function run(input) {
  const result = spawnSync(process.execPath, [subagentStatuslinePath], {
    encoding: 'utf8', input: typeof input === 'string' ? input : JSON.stringify(input),
  });
  const rows = result.stdout.trim() === '' ? [] : result.stdout.trim().split('\n').map(JSON.parse);
  return { ...result, rows };
}

function renderedRow(input) {
  const { status, stderr, rows } = run(input);
  assert.equal(status, 0, stderr);
  assert.equal(rows.length, 1);
  return rows[0];
}

test('renders identity, description, model, and context from the payload', (t) => {
  const row = renderedRow({
    transcript_path: createSession(t),
    tasks: [{
      id: 'a1', name: 'researcher', description: 'Investigate auth', tokenCount: 50_000,
      model: 'claude-opus-5-5', effort: 'high', contextWindowSize: 200_000,
    }],
  });

  assert.deepEqual(row, {
    id: 'a1',
    content: [
      `${COLORS.cyan}researcher${COLORS.reset}`,
      'Investigate auth',
      `${COLORS.blue}claude-opus-5-5•high${COLORS.reset}`,
      `${COLORS.green}25%/200k${COLORS.reset}`,
    ].join(' · '),
  });
});

test('names an unnamed subagent by its agent type and marks inherited effort', (t) => {
  const row = renderedRow({
    transcript_path: createSession(t, { a1: 'Explore' }),
    tasks: [{ id: 'a1', description: 'Probe', model: 'claude-opus-5-5', tokenCount: 8_894, contextWindowSize: 200_000 }],
  });

  assert.equal(stripAnsi(row.content), 'Explore · Probe · claude-opus-5-5•inherit · 4%/200k');
});

test('shows a numeric effort budget as written', (t) => {
  const row = renderedRow({ transcript_path: createSession(t), tasks: [{ id: 'a1', name: 'r', model: 'm', effort: 16_000 }] });

  assert.equal(stripAnsi(row.content), 'r · m•16000');
});

test('keeps the default row until the subagent has an identity', (t) => {
  const { status, rows } = run({ transcript_path: createSession(t), tasks: [{ id: 'a1', description: 'Starting' }] });

  assert.equal(status, 0);
  assert.deepEqual(rows, []);
});

test('flattens control characters in model-written text', (t) => {
  const row = renderedRow({
    transcript_path: createSession(t),
    tasks: [{ id: 'a1', name: 'r', description: 'line one\n\x1b[31mline two\x07' }],
  });

  assert.equal(stripAnsi(row.content), 'r · line one line two');
});

test('colors context pressure', (t) => {
  const transcriptPath = createSession(t);
  const contextSegment = (tokenCount) => renderedRow({
    transcript_path: transcriptPath,
    tasks: [{ id: 'a1', name: 'r', tokenCount, contextWindowSize: 100 }],
  }).content.split(' · ').at(-1);

  assert.equal(contextSegment(69), `${COLORS.green}69%/100${COLORS.reset}`);
  assert.equal(contextSegment(70), `${COLORS.yellow}70%/100${COLORS.reset}`);
  assert.equal(contextSegment(85), `${COLORS.red}85%/100${COLORS.reset}`);
});

test('fails on malformed input without partial output', () => {
  const result = run('{not-json');

  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, '');
});

'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const subagentStatuslinePath = path.join(__dirname, '..', 'files', 'claude', 'subagent-statusline.js');
const COLORS = Object.freeze({ cyan: '\x1b[96m', green: '\x1b[92m', yellow: '\x1b[93m', blue: '\x1b[94m', red: '\x1b[91m', reset: '\x1b[0m' });

function runStatusline(input) {
  return spawnSync(process.execPath, [subagentStatuslinePath], {
    encoding: 'utf8', input: typeof input === 'string' ? input : JSON.stringify(input),
  });
}

function stripAnsi(value) {
  return value.replace(/\x1b\[[0-9;]*m/g, '');
}

test('renders name, description, tokens, supplied model, and context in order', () => {
  const result = runStatusline({
    columns: 1,
    tasks: [{
      id: 'agent-1', name: 'researcher', description: 'Investigate auth', tokenCount: 50_000,
      model: 'claude-opus-4-8', contextWindowSize: 200_000, status: 'running',
    }],
  });
  const content = [
    `${COLORS.cyan}researcher${COLORS.reset}`,
    'Investigate auth',
    '50.0k tokens',
    `${COLORS.blue}claude-opus-4-8${COLORS.reset}`,
    `${COLORS.green}25%/200k${COLORS.reset}`,
  ].join(' · ');

  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, `${JSON.stringify({ id: 'agent-1', content })}\n`);
});

test('uses task.name only for identity and task.description only for description', () => {
  const result = runStatusline({
    tasks: [
      { id: 'named', name: '   ', label: 'Ignore label', type: 'local_agent', description: '  ', status: 'failed' },
      { id: 'described', name: 'worker', description: 'Review auth', label: 'Ignore label', type: 'remote_agent' },
    ],
  });
  const rows = result.stdout.trimEnd().split('\n').map(JSON.parse);

  assert.deepEqual(rows, [
    { id: 'named', content: `${COLORS.cyan}agent${COLORS.reset}` },
    { id: 'described', content: `${COLORS.cyan}worker${COLORS.reset} · Review auth` },
  ]);
});

test('formats valid tokenCount values without tokenSamples', () => {
  const result = runStatusline({
    tasks: [
      { id: 'zero', name: 'zero', tokenCount: 0, tokenSamples: [99_999] },
      { id: 'small', name: 'small', tokenCount: 999 },
      { id: 'thousand', name: 'thousand', tokenCount: 1_000 },
      { id: 'million', name: 'million', tokenCount: 1_234_567 },
      { id: 'invalid', name: 'invalid', tokenCount: -1 },
    ],
  });
  const rows = result.stdout.trimEnd().split('\n').map(JSON.parse);

  assert.deepEqual(rows.map(({ content }) => stripAnsi(content)), [
    'zero · 0 tokens', 'small · 999 tokens', 'thousand · 1.0k tokens', 'million · 1.2m tokens', 'invalid',
  ]);
});

test('derives rounded, clamped context only from valid tokenCount and capacity', () => {
  const result = runStatusline({
    tasks: [
      { id: 'zero', name: 'zero', tokenCount: 0, contextWindowSize: 200_000 },
      { id: 'warning', name: 'warning', tokenCount: 141_000, contextWindowSize: 200_000 },
      { id: 'critical', name: 'critical', tokenCount: 250_000, contextWindowSize: 200_000 },
      { id: 'invalid-count', name: 'invalid-count', tokenCount: -1, contextWindowSize: 200_000 },
      { id: 'invalid-capacity', name: 'invalid-capacity', tokenCount: 1, contextWindowSize: 0 },
    ],
  });
  const rows = Object.fromEntries(result.stdout.trimEnd().split('\n').map((line) => {
    const row = JSON.parse(line); return [row.id, row.content];
  }));

  assert.equal(rows.zero, `${COLORS.cyan}zero${COLORS.reset} · 0 tokens · ${COLORS.green}0%/200k${COLORS.reset}`);
  assert.equal(rows.warning, `${COLORS.cyan}warning${COLORS.reset} · 141.0k tokens · ${COLORS.yellow}71%/200k${COLORS.reset}`);
  assert.equal(rows.critical, `${COLORS.cyan}critical${COLORS.reset} · 250.0k tokens · ${COLORS.red}100%/200k${COLORS.reset}`);
  assert.equal(rows['invalid-count'], `${COLORS.cyan}invalid-count${COLORS.reset}`);
  assert.equal(rows['invalid-capacity'], `${COLORS.cyan}invalid-capacity${COLORS.reset} · 1 tokens`);
});

test('sanitizes description and model while preserving supplied model text', () => {
  const result = runStatusline({
    tasks: [{ id: 'escaped', name: 'name\n', description: 'line "\x1b[31mone\x1b[0m"\nline two', model: 'opus\x1b[31m-v2' }],
  });

  assert.deepEqual(JSON.parse(result.stdout), {
    id: 'escaped',
    content: `${COLORS.cyan}name${COLORS.reset} · line "one" line two · ${COLORS.blue}opus-v2${COLORS.reset}`,
  });
});

test('fails malformed top-level input without partial stdout', () => {
  for (const input of ['{not-json', '[]', '{}', '{"tasks":{}}']) {
    const result = runStatusline(input);
    assert.notEqual(result.status, 0, input);
    assert.equal(result.stdout, '', input);
    assert.equal(result.stderr, 'subagent-statusline: invalid input\n', input);
  }
});

test('emits one escaped JSON line per task with a valid string id', () => {
  const result = runStatusline({ tasks: [{ id: 'a"b', name: 'worker' }, null, {}, { id: '   ', name: 'blank id' }, { id: 42, name: 'numeric id' }] });

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), { id: 'a"b', content: `${COLORS.cyan}worker${COLORS.reset}` });
});

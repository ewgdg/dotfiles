'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const statuslinePath = path.join(__dirname, '..', 'files', 'claude', 'statusline.js');
const {
  COLORS,
  calculateCacheHit,
  formatContextWindowSize,
  normalizeInput,
  readGitBranch,
  renderStatusline,
} = require(statuslinePath);

function createTempDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-statusline-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test('uses the API context percentage directly, including zero', () => {
  const normalized = normalizeInput({
    context_window: {
      context_window_size: 272_000,
      used_percentage: 0,
      current_usage: {
        input_tokens: 2_000,
        cache_creation_input_tokens: 10_000,
        cache_read_input_tokens: 124_000,
      },
    },
  });

  assert.equal(normalized.contextPercentage, 0);
  assert.equal(normalized.contextWindowSize, 272_000);
});

test('renders every available context value independently', () => {
  assert.match(renderStatusline({ contextPercentage: 72.34, contextWindowSize: 200_000 }), /72\.3%\/200k/);
  assert.match(renderStatusline({ contextWindowSize: 200_000 }), /\?\/200k/);
  assert.match(renderStatusline({ contextPercentage: 0 }), /0\.0%\/\?/);
  assert.doesNotMatch(renderStatusline({}), /%\/|\?\/\?/);
});

test('calculates cache hit only from valid non-negative token counts', () => {
  assert.equal(calculateCacheHit({ input_tokens: 100, cache_read_input_tokens: 900 }), 90);
  assert.equal(calculateCacheHit({ input_tokens: 0, cache_read_input_tokens: 0 }), undefined);
  assert.equal(calculateCacheHit({ input_tokens: -1, cache_read_input_tokens: 1 }), undefined);
  assert.equal(calculateCacheHit({ input_tokens: '1', cache_read_input_tokens: 1 }), undefined);
  assert.equal(calculateCacheHit(undefined), undefined);
});

test('formats context-window sizes', () => {
  assert.equal(formatContextWindowSize(999), '999');
  assert.equal(formatContextWindowSize(1_000), '1k');
  assert.equal(formatContextWindowSize(199_900), '200k');
  assert.equal(formatContextWindowSize(1_000_000), '1.0m');
  assert.equal(formatContextWindowSize(1_250_000), '1.3m');
});

test('renders context, model, quotas, and a branch', () => {
  const output = renderStatusline({
    currentDirectory: '/workspace/project',
    modelName: 'Claude Opus 4.8',
    outputStyle: 'concise',
    effortLevel: 'high',
    contextPercentage: 72.34,
    contextWindowSize: 200_000,
    cacheHitPercentage: 81,
    fiveHourUsedPercentage: 35,
    sevenDayUsedPercentage: 95,
  }, 'feature/a-very-long-branch-name');

  assert.equal(output,
    `${COLORS.hint}/workspace/project${COLORS.reset}`
      + ` ${COLORS.green}[feature/a-very-long-branc]${COLORS.reset}\n`
      + ` ${COLORS.blue}Opus 4.8:concise•high${COLORS.reset}`
      + ` ${COLORS.yellow}72.3%/200k${COLORS.reset}`
      + ` ${COLORS.blue}CH:81%${COLORS.reset}`
      + ` ${COLORS.green}5h:65%${COLORS.reset}`
      + ` ${COLORS.red}7d:5%${COLORS.reset}`,
  );
});

test('omits absent segments without JavaScript sentinel values', () => {
  const output = renderStatusline({ currentDirectory: '/fallback' });

  assert.equal(output, `${COLORS.hint}/fallback${COLORS.reset}\n`);
  assert.doesNotMatch(output, /null|undefined|NaN|Infinity/);
});

test('reads symbolic and detached Git branches without shell interpolation', () => {
  const calls = [];
  const symbolicSpawn = (...arguments_) => {
    calls.push(arguments_);
    return { status: 0, stdout: 'main\n' };
  };

  assert.equal(readGitBranch('/workspace', symbolicSpawn), 'main');
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'git');
  assert.deepEqual(calls[0][1], ['symbolic-ref', '--quiet', '--short', 'HEAD']);
  assert.equal(calls[0][2].shell, false);
  assert.equal(calls[0][2].env.GIT_OPTIONAL_LOCKS, '0');

  const detachedSpawn = (command, arguments_) => {
    if (arguments_[0] === 'symbolic-ref') return { status: 1, stdout: '' };
    return { status: 0, stdout: 'abc1234\n' };
  };
  assert.equal(readGitBranch('/workspace', detachedSpawn), 'abc1234');
});

test('CLI displays the reported zero instead of recovering current usage', (t) => {
  const workingDirectory = createTempDirectory(t);
  const result = spawnSync(process.execPath, [statuslinePath], {
    cwd: workingDirectory,
    encoding: 'utf8',
    env: { ...process.env, PATH: '' },
    input: JSON.stringify({
      workspace: { current_dir: workingDirectory },
      context_window: {
        context_window_size: 272_000,
        used_percentage: 0,
        current_usage: { input_tokens: 2_000, cache_creation_input_tokens: 10_000, cache_read_input_tokens: 124_000 },
      },
    }),
  });

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /0\.0%\/272k/);
  assert.doesNotMatch(result.stdout, /50\.0%\/272k/);
});

test('CLI tolerates malformed JSON without invalid output', (t) => {
  const workingDirectory = createTempDirectory(t);
  const result = spawnSync(process.execPath, [statuslinePath], { cwd: workingDirectory, encoding: 'utf8', input: '{not-json' });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, `${COLORS.hint}${workingDirectory}${COLORS.reset}\n`);
});

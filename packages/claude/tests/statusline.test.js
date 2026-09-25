'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const statuslinePath = path.join(__dirname, '..', 'files', 'claude', 'statusline.js');
const { COLORS, renderStatusline } = require(statuslinePath);

const NOW_MILLISECONDS = 1_790_000_000_000;
const NOW_SECONDS = NOW_MILLISECONDS / 1_000;

function stripAnsi(value) {
  return value.replace(/\x1b\[[0-9;]*m/g, '');
}

function render(input, gitBranch) {
  return stripAnsi(renderStatusline(input, { gitBranch, nowMilliseconds: NOW_MILLISECONDS }));
}

function createTempDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-statusline-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function runCli(input, cwd, env = process.env) {
  return spawnSync(process.execPath, [statuslinePath], { cwd, env, encoding: 'utf8', input: JSON.stringify(input) });
}

function git(cwd, ...args) {
  const result = spawnSync('git', args, { cwd, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
}

test('renders location, model, context, cache hit, and quotas', () => {
  const output = render({
    workspace: { current_dir: path.join(os.homedir(), 'project') },
    model: { display_name: 'Claude Opus 5.5 (1M context)' },
    output_style: { name: 'explanatory' },
    effort: { level: 'high' },
    context_window: {
      context_window_size: 1_000_000,
      used_percentage: 7,
      current_usage: { input_tokens: 2, cache_creation_input_tokens: 1_192, cache_read_input_tokens: 65_082 },
    },
    rate_limits: {
      five_hour: { used_percentage: 3, resets_at: NOW_SECONDS + 3 * 3_600 + 37 * 60 },
      seven_day: { used_percentage: 20, resets_at: NOW_SECONDS + 4 * 86_400 + 12 * 3_600 },
    },
  }, 'main');

  assert.equal(output, '~/project [main]\n Opus 5.5 (1M context):explanatory•high 7.0%/1.0m CH:98% 3h37m:97% 4d12h:80%');
});

test('uses the reported context percentage, including zero, instead of recalculating it', () => {
  const output = render({
    context_window: {
      context_window_size: 272_000,
      used_percentage: 0,
      current_usage: { input_tokens: 2_000, cache_creation_input_tokens: 10_000, cache_read_input_tokens: 124_000 },
    },
  });

  assert.match(output, / 0\.0%\/272k /);
});

test('marks whichever context value is unknown', () => {
  assert.match(render({ context_window: { context_window_size: 272_000 } }), /\?\/272k/);
  assert.match(render({ context_window: { used_percentage: 26 } }), /26\.0%\/\?/);
  assert.doesNotMatch(render({}), /%|\//);
});

test('colors context pressure', () => {
  const contextSegment = (usedPercentage) => renderStatusline(
    { context_window: { context_window_size: 200_000, used_percentage: usedPercentage } },
    { nowMilliseconds: NOW_MILLISECONDS },
  );

  assert.ok(contextSegment(69).includes(`${COLORS.green}69.0%`));
  assert.ok(contextSegment(70).includes(`${COLORS.yellow}70.0%`));
  assert.ok(contextSegment(85).includes(`${COLORS.red}85.0%`));
});

test('labels quotas with the window name when the reset time is unknown', () => {
  const output = render({ rate_limits: { five_hour: { used_percentage: 95 }, seven_day: { used_percentage: 75, resets_at: 'soon' } } });

  assert.match(output, /5h:5% 7d:25%$/);
});

test('omits segments that Claude Code did not report', () => {
  assert.equal(render({ workspace: { current_dir: '/srv/app' } }), '/srv/app\n');
});

test('CLI shows the branch, or the short commit when HEAD is detached', (t) => {
  const repository = createTempDirectory(t);
  git(repository, 'init', '--quiet', '--initial-branch', 'feature/statusline');

  assert.match(stripAnsi(runCli({ workspace: { current_dir: repository } }, repository).stdout), /\[feature\/statusline\]/);

  git(repository, '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '--quiet', '--allow-empty', '-m', 'init');
  git(repository, 'checkout', '--quiet', '--detach');
  assert.match(stripAnsi(runCli({ workspace: { current_dir: repository } }, repository).stdout), /\[[0-9a-f]{7,}\]/);
});

test('CLI omits the branch outside a Git repository', (t) => {
  const directory = createTempDirectory(t);
  const result = runCli({ workspace: { current_dir: directory } }, directory);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(stripAnsi(result.stdout), `${directory}\n`);
});

test('CLI marks the branch unknown when Git fails inside a repository', (t) => {
  const repository = createTempDirectory(t);
  git(repository, 'init', '--quiet');
  const brokenConfig = path.join(repository, 'broken.gitconfig');
  fs.writeFileSync(brokenConfig, '[unterminated\n');
  const result = runCli({ workspace: { current_dir: repository } }, repository, { ...process.env, GIT_CONFIG_GLOBAL: brokenConfig });

  assert.equal(result.status, 0, result.stderr);
  assert.match(stripAnsi(result.stdout), /\[\?\]/);
});

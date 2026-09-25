'use strict';

const fs = require('node:fs');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

const COLORS = Object.freeze({
  hint: '\x1b[90m',
  cyan: '\x1b[96m',
  green: '\x1b[92m',
  yellow: '\x1b[93m',
  blue: '\x1b[94m',
  red: '\x1b[91m',
  reset: '\x1b[0m',
});

const CONTEXT_WARNING_PERCENTAGE = 70;
const CONTEXT_CRITICAL_PERCENTAGE = 85;
const QUOTA_WARNING_REMAINING_PERCENTAGE = 30;
const QUOTA_CRITICAL_REMAINING_PERCENTAGE = 10;
const BRANCH_MAX_CHARACTERS = 25;
const GIT_TIMEOUT_MS = 500;
// `git symbolic-ref --quiet` exits 1 for a detached HEAD.
const GIT_DETACHED_HEAD_STATUS = 1;

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE;
const SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR;

function finiteNumber(value) {
  return Number.isFinite(value) ? value : undefined;
}

function nonEmptyString(value) {
  return typeof value === 'string' && value.trim() !== '' ? value : undefined;
}

function colored(text, color) {
  return `${color}${text}${COLORS.reset}`;
}

function clampPercentage(value) {
  return Math.min(100, Math.max(0, value));
}

function contextColor(percentage) {
  const rounded = Math.round(percentage);
  if (rounded >= CONTEXT_CRITICAL_PERCENTAGE) return COLORS.red;
  if (rounded >= CONTEXT_WARNING_PERCENTAGE) return COLORS.yellow;
  return COLORS.green;
}

function formatContextWindowSize(size) {
  if (size >= 1_000_000) return `${(size / 1_000_000).toFixed(1)}m`;
  if (size >= 1_000) return `${Math.round(size / 1_000)}k`;
  return String(size);
}

// Show the two largest units, rounded down: 3d4h, 20h5m, 47m.
function formatTimeUntilReset(seconds) {
  const remaining = Math.max(0, seconds);
  const days = Math.floor(remaining / SECONDS_PER_DAY);
  const hours = Math.floor((remaining % SECONDS_PER_DAY) / SECONDS_PER_HOUR);
  const minutes = Math.floor((remaining % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  if (days > 0) return `${days}d${hours}h`;
  if (hours > 0) return `${hours}h${minutes}m`;
  return `${minutes}m`;
}

function abbreviateHomeDirectory(directory, homeDirectory = os.homedir()) {
  if (directory === homeDirectory) return '~';
  return directory.startsWith(`${homeDirectory}/`) ? `~${directory.slice(homeDirectory.length)}` : directory;
}

// Returns the branch, the short commit for a detached HEAD, undefined outside a repository, or '?' on failure.
function readGitBranch(directory) {
  const git = (...args) => spawnSync('git', args, {
    cwd: directory,
    encoding: 'utf8',
    // LC_ALL=C keeps the stderr match below independent of the user's locale.
    env: { ...process.env, GIT_OPTIONAL_LOCKS: '0', LC_ALL: 'C' },
    timeout: GIT_TIMEOUT_MS,
  });

  const symbolicRef = git('symbolic-ref', '--quiet', '--short', 'HEAD');
  if (symbolicRef.error) return '?';
  if (symbolicRef.status === 0) return symbolicRef.stdout.trim();
  if (symbolicRef.status !== GIT_DETACHED_HEAD_STATUS) {
    // Exit 128 also covers real failures such as untrusted repositories; only a missing repository hides the segment.
    return symbolicRef.stderr.includes('not a git repository') ? undefined : '?';
  }

  const shortCommit = git('rev-parse', '--short', 'HEAD');
  return !shortCommit.error && shortCommit.status === 0 ? shortCommit.stdout.trim() : '?';
}

// Share of the latest request's input served from the prompt cache.
function cacheHitPercentage(usage) {
  const cacheRead = finiteNumber(usage?.cache_read_input_tokens) ?? 0;
  const total = (finiteNumber(usage?.input_tokens) ?? 0)
    + (finiteNumber(usage?.cache_creation_input_tokens) ?? 0)
    + cacheRead;
  return total > 0 ? Math.round(clampPercentage((cacheRead / total) * 100)) : undefined;
}

function pathSegment(directory) {
  return colored(directory === undefined ? '?' : abbreviateHomeDirectory(directory), COLORS.hint);
}

function gitSegment(branch) {
  if (branch === undefined) return '';
  return colored(`[${Array.from(branch).slice(0, BRANCH_MAX_CHARACTERS).join('')}]`, COLORS.green);
}

function modelSegment(input) {
  const modelName = nonEmptyString(input.model?.display_name);
  if (modelName === undefined) return '';
  const outputStyle = nonEmptyString(input.output_style?.name);
  const effortLevel = nonEmptyString(input.effort?.level);
  const styleSuffix = outputStyle === undefined || outputStyle === 'default' ? '' : `:${outputStyle}`;
  const effortSuffix = effortLevel === undefined ? '' : `•${effortLevel}`;
  return colored(`${modelName.replace(/^Claude /, '')}${styleSuffix}${effortSuffix}`, COLORS.blue);
}

// Uses the reported percentage as-is; before the first response only the capacity is known.
function contextSegment(contextWindow) {
  const percentage = finiteNumber(contextWindow?.used_percentage);
  const size = finiteNumber(contextWindow?.context_window_size);
  if (percentage === undefined && size === undefined) return '';
  const used = percentage === undefined ? '?' : `${clampPercentage(percentage).toFixed(1)}%`;
  const capacity = size === undefined ? '?' : formatContextWindowSize(size);
  return colored(`${used}/${capacity}`, percentage === undefined ? COLORS.yellow : contextColor(percentage));
}

function cacheHitSegment(usage) {
  const percentage = cacheHitPercentage(usage);
  return percentage === undefined ? '' : colored(`CH:${percentage}%`, COLORS.blue);
}

function quotaColor(remainingPercentage) {
  if (remainingPercentage < QUOTA_CRITICAL_REMAINING_PERCENTAGE) return COLORS.red;
  if (remainingPercentage < QUOTA_WARNING_REMAINING_PERCENTAGE) return COLORS.yellow;
  return COLORS.green;
}

// The time until reset replaces the window name, because it is what the user acts on.
function quotaSegment(windowLabel, quota, nowMilliseconds) {
  const usedPercentage = finiteNumber(quota?.used_percentage);
  if (usedPercentage === undefined) return '';
  const resetsAt = finiteNumber(quota.resets_at);
  const label = resetsAt === undefined ? windowLabel : formatTimeUntilReset(resetsAt - nowMilliseconds / 1_000);
  const remaining = 100 - Math.round(clampPercentage(usedPercentage));
  return colored(`${label}:${remaining}%`, quotaColor(remaining));
}

function renderStatusline(input, { gitBranch, nowMilliseconds = Date.now() } = {}) {
  const firstLine = [
    pathSegment(nonEmptyString(input.workspace?.current_dir)),
    gitSegment(gitBranch),
  ].filter(Boolean).join(' ');

  const secondLine = [
    modelSegment(input),
    contextSegment(input.context_window),
    cacheHitSegment(input.context_window?.current_usage),
    quotaSegment('5h', input.rate_limits?.five_hour, nowMilliseconds),
    quotaSegment('7d', input.rate_limits?.seven_day, nowMilliseconds),
  ].filter(Boolean).join(' ');

  return `${firstLine}\n${secondLine === '' ? '' : ` ${secondLine}`}`;
}

function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const directory = nonEmptyString(input.workspace?.current_dir) ?? process.cwd();
  process.stdout.write(renderStatusline(input, { gitBranch: readGitBranch(directory) }));
}

if (require.main === module) main();

module.exports = { COLORS, colored, contextColor, formatContextWindowSize, renderStatusline };

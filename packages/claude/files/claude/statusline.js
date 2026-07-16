'use strict';

const fs = require('node:fs');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

const COLORS = Object.freeze({
  hint: '[90m',
  cyan: '[96m',
  green: '[92m',
  yellow: '[93m',
  blue: '[94m',
  red: '[91m',
  reset: '[0m',
});

const GIT_TIMEOUT_MS = 500;
const GIT_MAX_BUFFER_BYTES = 1024 * 1024;

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

const MISSING = Symbol('missing');
const FAILED = Symbol('failed');

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function clampedPercentage(value) {
  const number = finiteNumber(value);
  return number === undefined ? undefined : Math.min(100, Math.max(0, number));
}

function classifyOptional(value, predicate) {
  if (value === undefined || value === null) {
    return MISSING;
  }
  return predicate(value) ? value : FAILED;
}

function nonEmptyString(value) {
  return typeof value === 'string' && value.trim() !== '';
}

function tokenCount(usage, field) {
  const value = usage[field];
  if (value === undefined || value === null) {
    return 0;
  }
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

function calculateCacheHitState(usage) {
  const inputTokens = tokenCount(usage, 'input_tokens');
  const cacheCreationTokens = tokenCount(usage, 'cache_creation_input_tokens');
  const cacheReadTokens = tokenCount(usage, 'cache_read_input_tokens');
  if ([inputTokens, cacheCreationTokens, cacheReadTokens].includes(undefined)) {
    return FAILED;
  }

  const totalTokens = inputTokens + cacheCreationTokens + cacheReadTokens;
  if (totalTokens <= 0) {
    return MISSING;
  }

  return Math.round(Math.min(100, Math.max(0, (cacheReadTokens / totalTokens) * 100)));
}

function calculateCacheHit(usage) {
  if (!isObject(usage)) {
    return undefined;
  }
  const cacheHit = calculateCacheHitState(usage);
  return typeof cacheHit === 'number' ? cacheHit : undefined;
}

function normalizeInput(input, fallbackDirectory = process.cwd()) {
  const payload = isObject(input) ? input : {};
  const workspaceState = classifyOptional(payload.workspace, isObject);
  const modelState = classifyOptional(payload.model, isObject);
  const outputStyleState = classifyOptional(payload.output_style, isObject);
  const contextWindowState = classifyOptional(payload.context_window, isObject);
  const effortState = classifyOptional(payload.effort, isObject);
  const rateLimitsState = classifyOptional(payload.rate_limits, isObject);

  const workspace = workspaceState === MISSING ? {} : workspaceState;
  const model = modelState === MISSING ? {} : modelState;
  const outputStyle = outputStyleState === MISSING ? {} : outputStyleState;
  const contextWindow = contextWindowState === MISSING ? {} : contextWindowState;
  const effort = effortState === MISSING ? {} : effortState;
  const rateLimits = rateLimitsState === MISSING ? {} : rateLimitsState;

  const directory = workspaceState === FAILED
    ? FAILED
    : classifyOptional(workspace.current_dir, nonEmptyString);
  const currentDirectory = directory === MISSING
    ? classifyOptional(fallbackDirectory, nonEmptyString)
    : directory;

  const contextPercentage = contextWindowState === FAILED
    ? FAILED
    : classifyOptional(contextWindow.used_percentage, (value) => finiteNumber(value) !== undefined);
  const contextWindowSize = contextWindowState === FAILED
    ? FAILED
    : classifyOptional(contextWindow.context_window_size, (value) => finiteNumber(value) !== undefined && value > 0);
  const currentUsage = contextWindowState === FAILED
    ? FAILED
    : classifyOptional(contextWindow.current_usage, isObject);

  const fiveHour = rateLimitsState === FAILED
    ? FAILED
    : classifyOptional(rateLimits.five_hour, isObject);
  const sevenDay = rateLimitsState === FAILED
    ? FAILED
    : classifyOptional(rateLimits.seven_day, isObject);
  const quotaPercentage = (quota) => {
    if (quota === MISSING || quota === FAILED) {
      return quota;
    }
    return classifyOptional(quota.used_percentage, (value) => finiteNumber(value) !== undefined);
  };

  return {
    currentDirectory,
    modelName: modelState === FAILED ? FAILED : classifyOptional(model.display_name, nonEmptyString),
    outputStyle: outputStyleState === FAILED ? FAILED : classifyOptional(outputStyle.name, nonEmptyString),
    effortLevel: effortState === FAILED ? FAILED : classifyOptional(effort.level, nonEmptyString),
    contextWindowSize,
    contextPercentage,
    cacheHitPercentage: currentUsage === MISSING || currentUsage === FAILED
      ? currentUsage
      : calculateCacheHitState(currentUsage),
    fiveHourUsedPercentage: quotaPercentage(fiveHour),
    sevenDayUsedPercentage: quotaPercentage(sevenDay),
  };
}

function formatContextWindowSize(size) {
  if (size >= 1_000_000) {
    return `${(size / 1_000_000).toFixed(1)}m`;
  }
  if (size >= 1_000) {
    return `${Math.round(size / 1_000)}k`;
  }
  return String(size);
}

function readGitBranchState(currentDirectory, spawn = spawnSync) {
  const options = {
    cwd: currentDirectory,
    encoding: 'utf8',
    env: { ...process.env, GIT_OPTIONAL_LOCKS: '0' },
    maxBuffer: GIT_MAX_BUFFER_BYTES,
    shell: false,
    timeout: GIT_TIMEOUT_MS,
    windowsHide: true,
  };

  try {
    const symbolicRef = spawn('git', ['symbolic-ref', '--quiet', '--short', 'HEAD'], options);
    if (!symbolicRef.error && symbolicRef.status === 0) {
      const branch = symbolicRef.stdout.trim();
      return branch === '' ? FAILED : branch;
    }

    if (symbolicRef.error) {
      return FAILED;
    }

    if (symbolicRef.status === 128) {
      const repositoryCheck = spawn('git', ['rev-parse', '--is-inside-work-tree'], options);
      return !repositoryCheck.error && repositoryCheck.status === 128 ? MISSING : FAILED;
    }

    if (symbolicRef.status !== 1) {
      return FAILED;
    }

    const detachedHead = spawn('git', ['rev-parse', '--short', 'HEAD'], options);
    if (detachedHead.error || detachedHead.status !== 0) {
      return FAILED;
    }
    const branch = detachedHead.stdout.trim();
    return branch === '' ? FAILED : branch;
  } catch {
    return FAILED;
  }
}

function readGitBranch(currentDirectory, spawn = spawnSync) {
  const branch = readGitBranchState(currentDirectory, spawn);
  return typeof branch === 'string' ? branch : undefined;
}

function truncateBranch(branch) {
  return Array.from(branch).slice(0, 25).join('');
}

function valueIsMissing(value) {
  return value === MISSING || value === undefined || value === null;
}

function valueIsFailed(value) {
  return value === FAILED;
}

function safeSegment(render, fallback) {
  try {
    return render();
  } catch {
    return fallback();
  }
}

function contextColor(contextPercentage) {
  const roundedPercentage = Math.round(contextPercentage);
  if (roundedPercentage >= 85) {
    return COLORS.red;
  }
  if (roundedPercentage >= 70) {
    return COLORS.yellow;
  }
  return COLORS.green;
}

function remainingQuotaSegment(label, usedPercentage) {
  if (valueIsMissing(usedPercentage)) {
    return '';
  }
  if (valueIsFailed(usedPercentage)) {
    return `${COLORS.yellow}${label}:?${COLORS.reset}`;
  }

  const remaining = 100 - Math.round(clampedPercentage(usedPercentage));
  let color = COLORS.green;
  if (remaining < 10) {
    color = COLORS.red;
  } else if (remaining < 30) {
    color = COLORS.yellow;
  }
  return `${color}${label}:${remaining}%${COLORS.reset}`;
}

function abbreviateHomeDirectory(directory, homeDirectory = os.homedir()) {
  if (directory === homeDirectory) {
    return '~';
  }
  return directory.startsWith(`${homeDirectory}/`) ? `~${directory.slice(homeDirectory.length)}` : directory;
}

function renderPathSegment(directory) {
  return safeSegment(
    () => {
      const displayDirectory = valueIsFailed(directory) || valueIsMissing(directory)
        ? '?'
        : abbreviateHomeDirectory(directory);
      return `${COLORS.hint}${displayDirectory}${COLORS.reset}`;
    },
    () => `${COLORS.hint}?${COLORS.reset}`,
  );
}

function renderGitSegment(gitBranch) {
  if (valueIsMissing(gitBranch)) {
    return '';
  }
  return safeSegment(
    () => `${COLORS.green}[${valueIsFailed(gitBranch) ? '?' : truncateBranch(gitBranch)}]${COLORS.reset}`,
    () => `${COLORS.green}[?]${COLORS.reset}`,
  );
}

function renderModelSegment(status) {
  if (valueIsMissing(status.modelName)) {
    return '';
  }
  return safeSegment(
    () => {
      let modelLabel = valueIsFailed(status.modelName) ? '?' : status.modelName.replace(/^Claude /, '');
      if (valueIsFailed(status.outputStyle)) {
        modelLabel += ':?';
      } else if (!valueIsMissing(status.outputStyle) && status.outputStyle !== 'default') {
        modelLabel += `:${status.outputStyle}`;
      }
      if (valueIsFailed(status.effortLevel)) {
        modelLabel += '•?';
      } else if (!valueIsMissing(status.effortLevel)) {
        modelLabel += `•${status.effortLevel}`;
      }
      return `${COLORS.blue}${modelLabel}${COLORS.reset}`;
    },
    () => `${COLORS.blue}?${COLORS.reset}`,
  );
}

function renderContextSegment(status) {
  const percentageMissing = valueIsMissing(status.contextPercentage);
  const capacityMissing = valueIsMissing(status.contextWindowSize);
  if (percentageMissing && capacityMissing) {
    return '';
  }
  return safeSegment(
    () => {
      const failedPercentage = valueIsFailed(status.contextPercentage);
      const percentage = failedPercentage ? undefined : clampedPercentage(status.contextPercentage);
      const value = percentageMissing || failedPercentage ? '?' : `${percentage.toFixed(1)}%`;
      const total = valueIsFailed(status.contextWindowSize) || capacityMissing
        ? '/?'
        : `/${formatContextWindowSize(status.contextWindowSize)}`;
      const color = failedPercentage || percentageMissing ? COLORS.yellow : contextColor(percentage);
      return `${color}${value}${total}${COLORS.reset}`;
    },
    () => `${COLORS.yellow}?${COLORS.reset}`,
  );
}

function renderCacheHitSegment(cacheHitPercentage) {
  if (valueIsMissing(cacheHitPercentage)) {
    return '';
  }
  return safeSegment(
    () => {
      const value = valueIsFailed(cacheHitPercentage)
        ? '?'
        : `${Math.round(clampedPercentage(cacheHitPercentage))}%`;
      return `${COLORS.blue}CH:${value}${COLORS.reset}`;
    },
    () => `${COLORS.blue}CH:?${COLORS.reset}`,
  );
}

function renderStatusline(status, gitBranch) {
  const safeStatus = isObject(status) ? status : {};
  const firstLine = [
    renderPathSegment(safeStatus.currentDirectory),
    renderGitSegment(gitBranch),
  ].filter(Boolean).join(' ');

  const secondLineSegments = [
    safeSegment(() => renderModelSegment(safeStatus), () => `${COLORS.blue}?${COLORS.reset}`),
    safeSegment(() => renderContextSegment(safeStatus), () => `${COLORS.yellow}?${COLORS.reset}`),
    safeSegment(() => renderCacheHitSegment(safeStatus.cacheHitPercentage), () => `${COLORS.blue}CH:?${COLORS.reset}`),
    safeSegment(
      () => remainingQuotaSegment('5h', safeStatus.fiveHourUsedPercentage),
      () => `${COLORS.yellow}5h:?${COLORS.reset}`,
    ),
    safeSegment(
      () => remainingQuotaSegment('7d', safeStatus.sevenDayUsedPercentage),
      () => `${COLORS.yellow}7d:?${COLORS.reset}`,
    ),
  ].filter(Boolean);

  const secondLine = secondLineSegments.length > 0 ? ` ${secondLineSegments.join(' ')}` : '';
  return `${firstLine}\n${secondLine}`;
}

function buildStatusline(input, options = {}) {
  const normalized = normalizeInput(input, options.fallbackDirectory ?? process.cwd());
  const gitBranch = options.gitBranch === undefined
    ? readGitBranchState(normalized.currentDirectory, options.spawnGit)
    : options.gitBranch;
  return renderStatusline(normalized, gitBranch);
}

function fallbackStatusline() {
  return `${COLORS.hint}?${COLORS.reset}`;
}

function parseInput(rawInput) {
  try {
    return rawInput.trim() === '' ? {} : JSON.parse(rawInput);
  } catch {
    return {};
  }
}

function main() {
  let rawInput = '';
  try {
    rawInput = fs.readFileSync(0, 'utf8');
  } catch {
    // Render the default state when stdin is temporarily unavailable.
  }
  process.stdout.write(buildStatusline(parseInput(rawInput)));
}

if (require.main === module) {
  try {
    main();
  } catch {
    try {
      process.stdout.write(fallbackStatusline());
    } catch {
      process.exitCode = 1;
    }
  }
}

module.exports = {
  COLORS,
  buildStatusline,
  calculateCacheHit,
  formatContextWindowSize,
  normalizeInput,
  readGitBranch,
  renderStatusline,
};

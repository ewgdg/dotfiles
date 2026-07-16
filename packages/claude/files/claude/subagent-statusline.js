'use strict';

const fs = require('node:fs');
const { COLORS } = require('./statusline.js');

const TERMINAL_ESCAPE_PATTERN = /\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b./g;
const CONTROL_CHARACTER_PATTERN = /\p{Cc}+/gu;
const CONTEXT_WARNING_PERCENTAGE = 70;
const CONTEXT_CRITICAL_PERCENTAGE = 85;

function nonEmptyString(value) {
  return typeof value === 'string' && value.trim() !== '';
}

function normalizedText(value) {
  if (typeof value !== 'string') return undefined;
  const normalized = value
    .replace(TERMINAL_ESCAPE_PATTERN, '')
    .replace(CONTROL_CHARACTER_PATTERN, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return normalized === '' ? undefined : normalized;
}

function color(text, ansiColor) {
  return `${ansiColor}${text}${COLORS.reset}`;
}

function contextColor(percentage) {
  if (percentage >= CONTEXT_CRITICAL_PERCENTAGE) return COLORS.red;
  if (percentage >= CONTEXT_WARNING_PERCENTAGE) return COLORS.yellow;
  return COLORS.green;
}

function validTokenCount(value) {
  return Number.isFinite(value) && value >= 0 ? value : undefined;
}

function formatTokenCount(count) {
  if (count < 1_000) return `${count} tokens`;
  if (count < 1_000_000) return `${(count / 1_000).toFixed(1)}k tokens`;
  return `${(count / 1_000_000).toFixed(1)}m tokens`;
}

function formatContextWindowSize(size) {
  if (size >= 1_000_000) return `${(size / 1_000_000).toFixed(1)}m`;
  if (size >= 1_000) return `${Math.round(size / 1_000)}k`;
  return String(size);
}

function contextPercentage(tokenCount, contextWindowSize) {
  if (tokenCount === undefined || !Number.isFinite(contextWindowSize) || contextWindowSize <= 0) {
    return undefined;
  }
  return Math.min(100, Math.max(0, Math.round((tokenCount / contextWindowSize) * 100)));
}

function renderTask(task) {
  const identity = normalizedText(task.name) ?? 'agent';
  const description = normalizedText(task.description);
  const tokenCount = validTokenCount(task.tokenCount);
  const model = normalizedText(task.model);
  const percentage = contextPercentage(tokenCount, task.contextWindowSize);
  const segments = [color(identity, COLORS.cyan)];

  if (description !== undefined) segments.push(description);
  if (tokenCount !== undefined) segments.push(formatTokenCount(tokenCount));
  if (model !== undefined) segments.push(color(model, COLORS.blue));
  if (percentage !== undefined) {
    segments.push(color(`${percentage}%/${formatContextWindowSize(task.contextWindowSize)}`, contextColor(percentage)));
  }

  return segments.join(' · ');
}

function parseInput(rawInput) {
  let input;
  try {
    input = JSON.parse(rawInput);
  } catch {
    return undefined;
  }
  if (input === null || typeof input !== 'object' || Array.isArray(input) || !Array.isArray(input.tasks)) {
    return undefined;
  }
  return input;
}

function main() {
  const input = parseInput(fs.readFileSync(0, 'utf8'));
  if (input === undefined) {
    process.stderr.write('subagent-statusline: invalid input\n');
    process.exitCode = 1;
    return;
  }

  const output = input.tasks
    .filter((task) => task !== null && typeof task === 'object' && nonEmptyString(task.id))
    .map((task) => JSON.stringify({ id: task.id, content: renderTask(task) }))
    .join('\n');
  if (output !== '') process.stdout.write(`${output}\n`);
}

main();

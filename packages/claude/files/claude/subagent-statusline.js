'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { StringDecoder } = require('node:string_decoder');
const { COLORS } = require('./statusline.js');

const TERMINAL_ESCAPE_PATTERN = /\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b./g;
const CONTROL_CHARACTER_PATTERN = /\p{Cc}+/gu;
const CONTEXT_WARNING_PERCENTAGE = 70;
const CONTEXT_CRITICAL_PERCENTAGE = 85;
const TRANSCRIPT_READ_BUFFER_SIZE = 64 * 1024;

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

function subagentFilePath(input, task, suffix) {
  if (typeof input.transcript_path !== 'string' || !nonEmptyString(task.id)) return undefined;

  const filename = `agent-${task.id}${suffix}`;
  if (path.basename(filename) !== filename) return undefined;

  const sessionDirectory = path.join(
    path.dirname(input.transcript_path),
    path.basename(input.transcript_path, path.extname(input.transcript_path)),
  );
  return path.join(sessionDirectory, 'subagents', filename);
}

function forEachTranscriptLine(transcriptPath, visit) {
  const fileDescriptor = fs.openSync(transcriptPath, 'r');
  const buffer = Buffer.allocUnsafe(TRANSCRIPT_READ_BUFFER_SIZE);
  const decoder = new StringDecoder('utf8');
  let remainder = '';
  try {
    let bytesRead;
    while ((bytesRead = fs.readSync(fileDescriptor, buffer, 0, buffer.length, null)) > 0) {
      remainder += decoder.write(buffer.subarray(0, bytesRead));
      let newlineIndex;
      while ((newlineIndex = remainder.indexOf('\n')) !== -1) {
        visit(remainder.slice(0, newlineIndex));
        remainder = remainder.slice(newlineIndex + 1);
      }
    }
    remainder += decoder.end();
    if (remainder !== '') visit(remainder);
  } finally {
    fs.closeSync(fileDescriptor);
  }
}

function persistedSubagentData(input, task) {
  // Gateway-backed subagents can report zero live progress despite persisting API usage.
  const transcriptPath = subagentFilePath(input, task, '.jsonl');
  if (transcriptPath === undefined) return undefined;

  let totalTokens = 0;
  let contextTokens;
  let agentType;
  let foundUsage = false;
  try {
    forEachTranscriptLine(transcriptPath, (line) => {
      try {
      const entry = JSON.parse(line);
      agentType ??= normalizedText(entry.attributionAgent);
      const usage = entry?.message?.usage;
      let currentContextTokens = 0;
      let hasCurrentContext = false;
      for (const field of ['input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens']) {
        const value = validTokenCount(usage?.[field]);
        if (value !== undefined) {
          totalTokens += value;
          foundUsage = true;
          if (field !== 'output_tokens') {
            currentContextTokens += value;
            hasCurrentContext = true;
          }
        }
      }
      if (hasCurrentContext && currentContextTokens > 0) contextTokens = currentContextTokens;
      } catch {
        // The transcript is append-only and may be read while its final line is incomplete.
      }
    });
  } catch {
    return undefined;
  }
  return foundUsage || agentType !== undefined
    ? { agentType, totalTokens: foundUsage ? totalTokens : undefined, contextTokens }
    : undefined;
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

function renderTask(input, task) {
  const taskName = normalizedText(task.name);
  const persistedData = persistedSubagentData(input, task);
  const identity = taskName ?? persistedData?.agentType;
  if (identity === undefined) return undefined;
  const description = normalizedText(task.description);
  const reportedTokenCount = validTokenCount(task.tokenCount);
  const tokenSpend = persistedData?.totalTokens ?? reportedTokenCount;
  const model = normalizedText(task.model);
  const percentage = contextPercentage(persistedData?.contextTokens ?? reportedTokenCount, task.contextWindowSize);
  const segments = [color(identity, COLORS.cyan)];

  if (description !== undefined) segments.push(description);
  if (tokenSpend !== undefined) segments.push(formatTokenCount(tokenSpend));
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
    .map((task) => {
      const content = renderTask(input, task);
      return content === undefined ? undefined : JSON.stringify({ id: task.id, content });
    })
    .filter((row) => row !== undefined)
    .join('\n');
  if (output !== '') process.stdout.write(`${output}\n`);
}

main();

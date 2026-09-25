'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { COLORS, colored, contextColor, formatContextWindowSize } = require('./statusline.js');

// Every subagent assistant entry carries model, effort, and usage, so the newest one sits near the end.
// Bounding the read keeps each refresh cheap no matter how long the transcript grows.
const TRANSCRIPT_TAIL_BYTES = 1024 * 1024;
const TERMINAL_ESCAPE_PATTERN = /\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b./g;
const CONTROL_CHARACTER_PATTERN = /\p{Cc}+/gu;
const CONTEXT_USAGE_FIELDS = ['input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'];

// Collapses model-written text into one plain line.
function plainText(value) {
  if (typeof value !== 'string') return undefined;
  const text = value
    .replace(TERMINAL_ESCAPE_PATTERN, '')
    .replace(CONTROL_CHARACTER_PATTERN, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return text === '' ? undefined : text;
}

function positiveNumber(value) {
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

function readFileOrUndefined(read) {
  try {
    return read();
  } catch (error) {
    // Claude Code writes a subagent's files only after it starts.
    if (error.code === 'ENOENT') return undefined;
    throw error;
  }
}

function readTail(filePath, byteCount) {
  const fileDescriptor = fs.openSync(filePath, 'r');
  try {
    const { size } = fs.fstatSync(fileDescriptor);
    const start = Math.max(0, size - byteCount);
    const buffer = Buffer.alloc(size - start);
    fs.readSync(fileDescriptor, buffer, 0, buffer.length, start);
    const lines = buffer.toString('utf8').split('\n');
    // A tail that starts mid-file begins with a cut line.
    return start > 0 ? lines.slice(1) : lines;
  } finally {
    fs.closeSync(fileDescriptor);
  }
}

function parseJsonLine(line) {
  try {
    return JSON.parse(line);
  } catch {
    // The transcript is append-only, so the final line may still be half-written.
    return undefined;
  }
}

function latestAssistantEntry(transcriptPath) {
  const lines = readFileOrUndefined(() => readTail(transcriptPath, TRANSCRIPT_TAIL_BYTES)) ?? [];
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const entry = parseJsonLine(lines[index]);
    if (entry?.type === 'assistant' && entry.message !== undefined) return entry;
  }
  return undefined;
}

function contextTokens(usage) {
  const total = CONTEXT_USAGE_FIELDS.reduce((sum, field) => sum + (positiveNumber(usage?.[field]) ?? 0), 0);
  return positiveNumber(total);
}

function subagentFiles(sessionTranscriptPath, taskId) {
  const sessionDirectory = path.join(
    path.dirname(sessionTranscriptPath),
    path.basename(sessionTranscriptPath, path.extname(sessionTranscriptPath)),
  );
  const base = path.join(sessionDirectory, 'subagents', `agent-${path.basename(taskId)}`);
  return { transcript: `${base}.jsonl`, meta: `${base}.meta.json` };
}

function readSubagentState(sessionTranscriptPath, taskId) {
  const files = subagentFiles(sessionTranscriptPath, taskId);
  const meta = readFileOrUndefined(() => JSON.parse(fs.readFileSync(files.meta, 'utf8')));
  return { agentType: meta?.agentType, latestEntry: latestAssistantEntry(files.transcript) };
}

function renderTask(task, { agentType, latestEntry }) {
  const identity = plainText(task.name) ?? plainText(agentType);
  // Without an identity, leave the row to Claude Code's default rendering.
  if (identity === undefined) return undefined;

  const model = plainText(task.model) ?? plainText(latestEntry?.message?.model);
  // Task effort is present only when set explicitly; inherited effort is visible only in the transcript.
  const effort = plainText(String(task.effort ?? latestEntry?.effort ?? ''));
  // Gateway-backed subagents have reported tokenCount 0 despite persisting API usage.
  const tokens = positiveNumber(task.tokenCount) ?? contextTokens(latestEntry?.message?.usage) ?? task.tokenCount;
  const windowSize = positiveNumber(task.contextWindowSize);

  const segments = [colored(identity, COLORS.cyan), plainText(task.description)];
  if (model !== undefined) segments.push(colored(effort === undefined ? model : `${model}•${effort}`, COLORS.blue));
  if (Number.isFinite(tokens) && windowSize !== undefined) {
    const percentage = Math.min(100, Math.max(0, Math.round((tokens / windowSize) * 100)));
    segments.push(colored(`${percentage}%/${formatContextWindowSize(windowSize)}`, contextColor(percentage)));
  }
  return segments.filter(Boolean).join(' · ');
}

function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const rows = input.tasks.flatMap((task) => {
    const content = renderTask(task, readSubagentState(input.transcript_path, task.id));
    return content === undefined ? [] : [JSON.stringify({ id: task.id, content })];
  });
  if (rows.length > 0) process.stdout.write(`${rows.join('\n')}\n`);
}

main();

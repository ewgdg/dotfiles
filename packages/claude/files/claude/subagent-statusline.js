'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { COLORS, colored, contextColor, formatContextWindowSize } = require('./statusline.js');

const TERMINAL_ESCAPE_PATTERN = /\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b./g;
const CONTROL_CHARACTER_PATTERN = /\p{Cc}+/gu;
// Claude Code sends a task's effort only when it is set for that subagent or the session was started with
// `--effort`. Otherwise the level comes from settings layers the statusline can't see, so it is read from the
// subagent's latest response, and shown as auto until the first response is written.
const AUTO_EFFORT_LABEL = 'auto';
const TRANSCRIPT_CHUNK_BYTES = 64 * 1024;
// Bounds each refresh's read; a single tool result line can span hundreds of KiB.
const TRANSCRIPT_SCAN_LIMIT_BYTES = 1024 * 1024;
const NEWLINE_BYTE = 0x0a;

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

// Claude Code keeps each subagent's files beside the session transcript: <session>/subagents/agent-<id>.<extension>.
function subagentFilePath(sessionTranscriptPath, taskId, extension) {
  const sessionDirectory = path.join(
    path.dirname(sessionTranscriptPath),
    path.basename(sessionTranscriptPath, path.extname(sessionTranscriptPath)),
  );
  return path.join(sessionDirectory, 'subagents', `agent-${path.basename(taskId)}.${extension}`);
}

// Unnamed tasks carry only a generic `type`; the agent type lives in the subagent's metadata file.
function readAgentType(sessionTranscriptPath, taskId) {
  try {
    return JSON.parse(fs.readFileSync(subagentFilePath(sessionTranscriptPath, taskId, 'meta.json'), 'utf8')).agentType;
  } catch (error) {
    // Claude Code writes the metadata file only after the subagent starts.
    if (error.code === 'ENOENT') return undefined;
    throw error;
  }
}

function responseEffort(line) {
  // Skips parsing lines that can't carry an effort, such as large tool results.
  if (!line.includes('"effort"')) return undefined;
  const entry = JSON.parse(line);
  return entry.type === 'assistant' ? entry.effort : undefined;
}

// Buffer#lastIndexOf treats a negative offset as counting from the end, so searching before index 0 is guarded.
function previousNewlineIndex(buffer, beforeIndex) {
  return beforeIndex > 0 ? buffer.lastIndexOf(NEWLINE_BYTE, beforeIndex - 1) : -1;
}

// Scans complete lines backward from the end of the file, so a refresh never reads the whole transcript.
function readLatestResponseEffort(transcriptPath) {
  let fileDescriptor;
  try {
    fileDescriptor = fs.openSync(transcriptPath, 'r');
  } catch (error) {
    // Claude Code writes the transcript only after the subagent starts.
    if (error.code === 'ENOENT') return undefined;
    throw error;
  }
  try {
    const fileSize = fs.fstatSync(fileDescriptor).size;
    const scanStart = Math.max(0, fileSize - TRANSCRIPT_SCAN_LIMIT_BYTES);
    let position = fileSize;
    // Bytes after the last newline seen so far; at the end of the file that is a line still being written.
    let unterminatedTail = Buffer.alloc(0);
    let isFileEnd = true;
    while (position > scanStart) {
      const chunkSize = Math.min(TRANSCRIPT_CHUNK_BYTES, position - scanStart);
      position -= chunkSize;
      const chunk = Buffer.alloc(chunkSize);
      fs.readSync(fileDescriptor, chunk, 0, chunkSize, position);
      const buffer = Buffer.concat([chunk, unterminatedTail]);
      // Splitting on the newline byte is UTF-8 safe: 0x0a never occurs inside a multi-byte character.
      let lineEnd = buffer.lastIndexOf(NEWLINE_BYTE);
      if (lineEnd === -1) {
        unterminatedTail = buffer;
        continue;
      }
      if (!isFileEnd) lineEnd = buffer.length;
      isFileEnd = false;
      let lineStart = previousNewlineIndex(buffer, lineEnd);
      while (lineStart !== -1) {
        const effort = responseEffort(buffer.toString('utf8', lineStart + 1, lineEnd));
        if (effort !== undefined) return effort;
        lineEnd = lineStart;
        lineStart = previousNewlineIndex(buffer, lineEnd);
      }
      unterminatedTail = buffer.subarray(0, lineEnd);
    }
    // The first line of the file has no newline before it.
    return position === 0 && !isFileEnd ? responseEffort(unterminatedTail.toString('utf8')) : undefined;
  } finally {
    fs.closeSync(fileDescriptor);
  }
}

function renderTask(task, agentType, effort) {
  const identity = plainText(task.name) ?? plainText(agentType);
  // Without an identity, leave the row to Claude Code's default rendering.
  if (identity === undefined) return undefined;

  const model = plainText(task.model);
  const effortLabel = plainText(String(effort ?? AUTO_EFFORT_LABEL));
  const windowSize = Number.isFinite(task.contextWindowSize) && task.contextWindowSize > 0 ? task.contextWindowSize : undefined;

  const segments = [colored(identity, COLORS.cyan), plainText(task.description)];
  if (model !== undefined) segments.push(colored(`${model}•${effortLabel}`, COLORS.blue));
  if (Number.isFinite(task.tokenCount) && windowSize !== undefined) {
    const percentage = Math.min(100, Math.max(0, Math.round((task.tokenCount / windowSize) * 100)));
    segments.push(colored(`${percentage}%/${formatContextWindowSize(windowSize)}`, contextColor(percentage)));
  }
  return segments.filter(Boolean).join(' · ');
}

function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const rows = input.tasks.flatMap((task) => {
    const agentType = task.name === undefined ? readAgentType(input.transcript_path, task.id) : undefined;
    const effort = task.effort ?? readLatestResponseEffort(subagentFilePath(input.transcript_path, task.id, 'jsonl'));
    const content = renderTask(task, agentType, effort);
    return content === undefined ? [] : [JSON.stringify({ id: task.id, content })];
  });
  if (rows.length > 0) process.stdout.write(`${rows.join('\n')}\n`);
}

main();

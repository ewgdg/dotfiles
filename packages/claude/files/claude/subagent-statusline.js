'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { COLORS, colored, contextColor, formatContextWindowSize } = require('./statusline.js');

const TERMINAL_ESCAPE_PATTERN = /\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b./g;
const CONTROL_CHARACTER_PATTERN = /\p{Cc}+/gu;
// Subagents inherit the session's effort live. Claude Code sends it when the session level is explicit and
// omits it only when the session is on auto, where each subagent's model resolves its own level.
const AUTO_EFFORT_LABEL = 'auto';

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

// Unnamed tasks carry only a generic `type`; the agent type lives in the subagent's metadata file.
function readAgentType(sessionTranscriptPath, taskId) {
  const sessionDirectory = path.join(
    path.dirname(sessionTranscriptPath),
    path.basename(sessionTranscriptPath, path.extname(sessionTranscriptPath)),
  );
  const metaPath = path.join(sessionDirectory, 'subagents', `agent-${path.basename(taskId)}.meta.json`);
  try {
    return JSON.parse(fs.readFileSync(metaPath, 'utf8')).agentType;
  } catch (error) {
    // Claude Code writes the metadata file only after the subagent starts.
    if (error.code === 'ENOENT') return undefined;
    throw error;
  }
}

function renderTask(task, agentType) {
  const identity = plainText(task.name) ?? plainText(agentType);
  // Without an identity, leave the row to Claude Code's default rendering.
  if (identity === undefined) return undefined;

  const model = plainText(task.model);
  const effort = task.effort === undefined ? AUTO_EFFORT_LABEL : plainText(String(task.effort));
  const windowSize = Number.isFinite(task.contextWindowSize) && task.contextWindowSize > 0 ? task.contextWindowSize : undefined;

  const segments = [colored(identity, COLORS.cyan), plainText(task.description)];
  if (model !== undefined) segments.push(colored(`${model}•${effort}`, COLORS.blue));
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
    const content = renderTask(task, agentType);
    return content === undefined ? [] : [JSON.stringify({ id: task.id, content })];
  });
  if (rows.length > 0) process.stdout.write(`${rows.join('\n')}\n`);
}

main();

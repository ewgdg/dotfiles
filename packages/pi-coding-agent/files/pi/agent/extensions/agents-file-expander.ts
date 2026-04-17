import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { getAgentDir, loadProjectContextFiles, type ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Box, Spacer, Text } from "@mariozechner/pi-tui";

type ExpansionIssue = string;

const BARE_REFERENCE_LINE_PATTERN = /^\s*@([^\s<>{}\[\]"'`(),;!?]+)\s*$/;
const QUOTED_REFERENCE_LINE_PATTERN = /^\s*@(["'])(.*)\1\s*$/;
const MESSAGE_TYPE = "agents-expanded";
const MESSAGE_TITLE = "Expanded context";

let cachedExpandedPrompt: string | undefined;

type ParsedReference = {
  reference: string;
};

type LoadedFileEntry = {
  path: string;
  displayPath: string;
};

type LoadedFileState = {
  entries: LoadedFileEntry[];
  seen: Set<string>;
};

type ExpandedFilesMessageDetails = {
  files: string[];
  issues: string[];
};

type ContextFile = {
  path: string;
  content: string;
};

function fileExists(filePath: string): boolean {
  return fs.existsSync(filePath) && fs.statSync(filePath).isFile();
}

function resolveReferencePath(reference: string, baseDir: string): string {
  const envMatch = reference.match(/^\$(\w+)(.*)$/) ?? reference.match(/^\$\{([^}]+)\}(.*)$/);
  if (envMatch) {
    const envName = envMatch[1];
    const suffix = envMatch[2] ?? "";
    const envValue = process.env[envName];
    if (envValue) {
      return path.isAbsolute(envValue + suffix) ? path.normalize(envValue + suffix) : path.resolve(baseDir, envValue + suffix);
    }
  }

  if (reference.startsWith("~/")) {
    return path.join(os.homedir(), reference.slice(2));
  }
  if (reference === "~") {
    return os.homedir();
  }
  if (path.isAbsolute(reference)) {
    return path.normalize(reference);
  }
  return path.resolve(baseDir, reference);
}

function canonicalize(filePath: string): string {
  return fs.realpathSync(filePath);
}

function formatDisplayPath(filePath: string, baseDir: string): string {
  const relativePath = path.relative(baseDir, filePath);
  if (relativePath && !relativePath.startsWith("..") && !path.isAbsolute(relativePath)) {
    return relativePath;
  }

  const homeDir = os.homedir();
  if (filePath.startsWith(homeDir)) {
    return `~${filePath.slice(homeDir.length)}`;
  }

  return filePath;
}

function recordLoadedFile(filePath: string, displayPath: string, state: LoadedFileState): void {
  if (state.seen.has(filePath)) {
    return;
  }

  state.seen.add(filePath);
  state.entries.push({ path: filePath, displayPath });
}

function unescapeQuotedReference(raw: string): string {
  let reference = "";
  let cursor = 0;

  while (cursor < raw.length) {
    const current = raw[cursor];
    if (current === "\\" && cursor + 1 < raw.length) {
      reference += raw[cursor + 1];
      cursor += 2;
      continue;
    }

    reference += current;
    cursor += 1;
  }

  return reference;
}

function parseWholeLineReference(line: string): ParsedReference | undefined {
  const quotedMatch = line.match(QUOTED_REFERENCE_LINE_PATTERN);
  if (quotedMatch) {
    const reference = unescapeQuotedReference(quotedMatch[2]);
    return reference ? { reference } : undefined;
  }

  const bareMatch = line.match(BARE_REFERENCE_LINE_PATTERN);
  if (bareMatch) {
    return { reference: bareMatch[1] };
  }

  return undefined;
}

function endsWithLineBreak(text: string): boolean {
  return /\r?\n$/.test(text);
}

function loadExpandedFile(
  filePath: string,
  baseDir: string,
  memo: Map<string, string>,
  issues: Set<ExpansionIssue>,
  stack: string[],
  loadedFiles: LoadedFileState,
): string {
  const canonicalPath = canonicalize(filePath);
  const cached = memo.get(canonicalPath);
  if (cached !== undefined) {
    return cached;
  }

  if (stack.includes(canonicalPath)) {
    throw new Error(`Cycle while expanding ${canonicalPath}`);
  }

  stack.push(canonicalPath);
  recordLoadedFile(canonicalPath, formatDisplayPath(canonicalPath, baseDir), loadedFiles);

  const raw = fs.readFileSync(canonicalPath, "utf8");
  const expanded = expandText(raw, path.dirname(canonicalPath), canonicalPath, memo, issues, stack, loadedFiles);

  stack.pop();
  memo.set(canonicalPath, expanded);
  return expanded;
}

function expandLine(
  line: string,
  baseDir: string,
  sourcePath: string,
  memo: Map<string, string>,
  issues: Set<ExpansionIssue>,
  stack: string[],
  loadedFiles: LoadedFileState,
): string {
  const reference = parseWholeLineReference(line);
  if (!reference) {
    return line;
  }

  const resolvedPath = resolveReferencePath(reference.reference, baseDir);
  if (!fileExists(resolvedPath)) {
    issues.add(`Missing reference in ${sourcePath}: @${reference.reference}`);
    return line;
  }

  try {
    return loadExpandedFile(resolvedPath, baseDir, memo, issues, stack, loadedFiles);
  } catch (error) {
    issues.add(
      `Failed to expand @${reference.reference} from ${sourcePath}: ${error instanceof Error ? error.message : String(error)}`,
    );
    return line;
  }
}

function expandText(
  text: string,
  baseDir: string,
  sourcePath: string,
  memo: Map<string, string>,
  issues: Set<ExpansionIssue>,
  stack: string[],
  loadedFiles: LoadedFileState,
): string {
  const segments = text.split(/(\r?\n)/);
  const chunks: string[] = [];

  for (let index = 0; index < segments.length; index += 2) {
    const body = segments[index] ?? "";
    const newline = segments[index + 1] ?? "";
    const expanded = expandLine(body, baseDir, sourcePath, memo, issues, stack, loadedFiles);
    chunks.push(expanded);
    if (newline && !endsWithLineBreak(expanded)) {
      chunks.push(newline);
    }
  }

  return chunks.join("");
}

function replaceContextBlocksInPrompt(
  prompt: string,
  contextFiles: ContextFile[],
  memo: Map<string, string>,
  issues: Set<ExpansionIssue>,
  loadedFiles: LoadedFileState,
): string {
  let expandedPrompt = prompt;
  let cursor = 0;

  for (const contextFile of contextFiles) {
    const expandedContent = expandText(
      contextFile.content,
      path.dirname(contextFile.path),
      contextFile.path,
      memo,
      issues,
      [],
      loadedFiles,
    );

    // This assumes loadProjectContextFiles() order matches buildSystemPrompt() context-file order.
    const blockIndex = expandedPrompt.indexOf(contextFile.content, cursor);
    if (blockIndex === -1) {
      issues.add(`Failed to replace expanded block for ${contextFile.path}`);
      continue;
    }

    expandedPrompt =
      expandedPrompt.slice(0, blockIndex) +
      expandedContent +
      expandedPrompt.slice(blockIndex + contextFile.content.length);
    cursor = blockIndex + expandedContent.length;
  }

  return expandedPrompt;
}

function buildExpandedPromptAndFiles(
  prompt: string,
  cwd: string,
): { expandedPrompt: string; files: string[]; issues: string[] } {
  const memo = new Map<string, string>();
  const issues = new Set<ExpansionIssue>();
  const loadedFiles: LoadedFileState = { entries: [], seen: new Set<string>() };
  const contextFiles = loadProjectContextFiles({ cwd, agentDir: getAgentDir() });

  const expandedPrompt = replaceContextBlocksInPrompt(prompt, contextFiles, memo, issues, loadedFiles);

  return {
    expandedPrompt,
    files: loadedFiles.entries.map((entry) => entry.displayPath),
    issues: Array.from(issues),
  };
}

function createExpandedMessageBox(details: ExpandedFilesMessageDetails, theme: any): Box {
  const box = new Box(1, 1, (t) => theme.bg("customMessageBg", t));
  box.addChild(new Text(theme.bold(MESSAGE_TITLE), 0, 0));
  box.addChild(new Spacer(1));

  if (details.files.length > 0) {
    for (const file of details.files) {
      box.addChild(new Text(theme.fg("customMessageLabel", "[+]") + theme.fg("dim", ` ${file}`), 0, 0));
    }
  }

  if (details.issues.length > 0) {
    for (const issue of details.issues) {
      box.addChild(new Text(theme.fg("warning", "[!]") + theme.fg("dim", ` ${issue}`), 0, 0));
    }
  }

  return box;
}

export default function agentsFileExpander(pi: ExtensionAPI) {
  pi.registerMessageRenderer<ExpandedFilesMessageDetails>(MESSAGE_TYPE, (message, _options, theme) => {
    return createExpandedMessageBox(message.details ?? { files: [] }, theme);
  });

  pi.on("session_start", async (_event, ctx) => {
    // Build once per session. before_agent_start fires every turn, so cache static expanded prompt here.
    const prompt = ctx.getSystemPrompt();
    const result = buildExpandedPromptAndFiles(prompt, ctx.cwd);
    cachedExpandedPrompt = result.expandedPrompt;

    if (ctx.hasUI && (result.files.length > 0 || result.issues.length > 0)) {
      pi.sendMessage(
        {
          customType: MESSAGE_TYPE,
          content: MESSAGE_TITLE,
          display: true,
          details: { files: result.files, issues: result.issues },
        },
        { triggerTurn: false },
      );
    } else if (result.issues.length > 0) {
      const firstIssue = result.issues[0];
      const message =
        result.issues.length === 1
          ? `AGENTS @file expansion warning: ${firstIssue}`
          : `AGENTS @file expansion warnings: ${firstIssue} (+${result.issues.length - 1} more)`;
      console.warn(`${message}\n${result.issues.join("\n")}`);
    }
  });

  pi.on("session_shutdown", () => {
    cachedExpandedPrompt = undefined;
  });

  pi.on("before_agent_start", async () => {
    if (cachedExpandedPrompt === undefined) {
      return undefined;
    }

    return {
      systemPrompt: cachedExpandedPrompt,
    };
  });
}

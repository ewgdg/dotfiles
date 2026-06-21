import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const COMMAND_NAME = "openrouter-controls";
const CONFIG_FILE_NAME = "pi-openrouter-controls.json";
const SERVER_TOOL_SEARCH = "openrouter:web_search";
const SERVER_TOOL_FETCH = "openrouter:web_fetch";

type JsonRecord = Record<string, unknown>;

type OpenRouterControlsConfig = {
  openrouter: {
    quantizations?: string[];
    webSearch?: boolean;
    webFetch?: boolean;
  };
};


function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getAgentDir(): string {
  const configuredAgentDir = process.env.PI_CODING_AGENT_DIR?.trim();
  return configuredAgentDir || join(homedir(), ".pi", "agent");
}

function getConfigPaths(cwd: string): string[] {
  return [join(getAgentDir(), CONFIG_FILE_NAME), join(cwd, ".pi", CONFIG_FILE_NAME)];
}

function readJsonObjectFile(path: string): JsonRecord {
  if (!existsSync(path)) return {};

  const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
  if (!isRecord(parsed)) {
    throw new Error(`Expected ${path} to contain a JSON object`);
  }
  return parsed;
}

function parseStringArray(value: unknown, context: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw new Error(`${context} must be an array of strings`);

  const items = value.map((item, index) => {
    if (typeof item !== "string") throw new Error(`${context}[${index}] must be a string`);
    return item.trim();
  }).filter(Boolean);

  return items.length > 0 ? items : undefined;
}

function parseBoolean(value: unknown, context: string): boolean | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "boolean") throw new Error(`${context} must be a boolean`);
  return value;
}

function parseRawConfig(raw: JsonRecord, path: string): Partial<OpenRouterControlsConfig> {
  const openrouter = isRecord(raw.openrouter) ? raw.openrouter : undefined;
  if (!openrouter) return {};

  const quantizations = parseStringArray(openrouter.quantizations, `${path}.openrouter.quantizations`);
  const webSearch = parseBoolean(openrouter.web_search, `${path}.openrouter.web_search`);
  const webFetch = parseBoolean(openrouter.web_fetch, `${path}.openrouter.web_fetch`);

  return {
    openrouter: {
      ...(quantizations ? { quantizations } : {}),
      ...(webSearch !== undefined ? { webSearch } : {}),
      ...(webFetch !== undefined ? { webFetch } : {}),
    },
  };
}

function mergePartialConfig(
  base: Partial<OpenRouterControlsConfig>,
  override: Partial<OpenRouterControlsConfig>,
): Partial<OpenRouterControlsConfig> {
  return {
    openrouter: {
      ...(base.openrouter ?? {}),
      ...(override.openrouter ?? {}),
    },
  };
}

function normalizeConfig(config: Partial<OpenRouterControlsConfig>): OpenRouterControlsConfig {
  return {
    openrouter: {
      ...(config.openrouter?.quantizations ? { quantizations: config.openrouter.quantizations } : {}),
      ...(config.openrouter?.webSearch !== undefined ? { webSearch: config.openrouter.webSearch } : {}),
      ...(config.openrouter?.webFetch !== undefined ? { webFetch: config.openrouter.webFetch } : {}),
    },
  };
}

function loadConfig(cwd: string = process.cwd()): OpenRouterControlsConfig {
  const globalConfig = readConfigFile(join(getAgentDir(), CONFIG_FILE_NAME));
  const projectConfig = readConfigFile(join(cwd, ".pi", CONFIG_FILE_NAME));
  return normalizeConfig(mergePartialConfig(globalConfig, projectConfig));
}

function readConfigFile(path: string): Partial<OpenRouterControlsConfig> {
  if (!existsSync(path)) return {};
  return parseRawConfig(readJsonObjectFile(path), path);
}

function isOpenRouterModel(model: ExtensionContext["model"]): boolean {
  return (model?.provider ?? "").toLowerCase() === "openrouter";
}

function updateOpenRouterControlsStatus(ctx: ExtensionContext, config: OpenRouterControlsConfig): void {
  if (!ctx.hasUI) return;

  const status = isOpenRouterModel(ctx.model)
    ? [
        config.openrouter.webSearch ? "🌐search" : undefined,
        config.openrouter.webFetch ? "🌐fetch" : undefined,
      ].filter(Boolean).join(" ")
    : "";

  ctx.ui.setStatus("00-openrouter-controls", status || undefined);
}

function areStringArraysEqual(left: unknown, right: unknown): boolean {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false;
  }
  return left.every((value, index) => value === right[index]);
}

function rewritePayload(payload: unknown, ctx: ExtensionContext, config: OpenRouterControlsConfig): unknown {
  if (!isOpenRouterModel(ctx.model) || !isRecord(payload)) {
    return undefined;
  }

  let nextPayload = payload;
  let changed = false;

  if (config.openrouter.quantizations && config.openrouter.quantizations.length > 0) {
    const currentProvider = isRecord(nextPayload.provider) ? nextPayload.provider : {};
    const nextProvider = { ...currentProvider, quantizations: config.openrouter.quantizations };
    if (!areStringArraysEqual(currentProvider.quantizations, nextProvider.quantizations)) {
      nextPayload = { ...nextPayload, provider: nextProvider };
      changed = true;
    }
  }

  const desiredTools: Array<{ type: string }> = [];
  if (config.openrouter.webSearch) desiredTools.push({ type: SERVER_TOOL_SEARCH });
  if (config.openrouter.webFetch) desiredTools.push({ type: SERVER_TOOL_FETCH });

  if (desiredTools.length > 0) {
    const currentTools = Array.isArray(nextPayload.tools) ? nextPayload.tools : [];
    const currentToolTypes = new Set(
      currentTools.flatMap((tool) => (isRecord(tool) && typeof tool.type === "string" ? [tool.type] : [])),
    );
    const mergedTools = [...currentTools];

    for (const tool of desiredTools) {
      if (!currentToolTypes.has(tool.type)) {
        mergedTools.push(tool);
        currentToolTypes.add(tool.type);
        changed = true;
      }
    }

    if (changed) {
      nextPayload = { ...nextPayload, tools: mergedTools };
    }
  }

  return changed ? nextPayload : undefined;
}

function formatStatus(config: OpenRouterControlsConfig, cwd: string): string {
  const lines = [
    `OpenRouter controls`,
    `Config: ${getConfigPaths(cwd).join(", ")}`,
    `quantizations: ${config.openrouter.quantizations?.join(", ") || "(none)"}`,
    `web_search: ${config.openrouter.webSearch ? "on" : "off"}`,
    `web_fetch: ${config.openrouter.webFetch ? "on" : "off"}`,
  ];
  return lines.join("\n");
}

export default function openRouterControls(pi: ExtensionAPI) {
  let config = loadConfig();

  pi.on("session_start", async (_event, ctx) => {
    config = loadConfig(ctx.cwd);
    updateOpenRouterControlsStatus(ctx, config);
  });

  pi.on("model_select", async (_event, ctx) => {
    updateOpenRouterControlsStatus(ctx, config);
  });

  pi.on("before_provider_request", async (event, ctx) => {
    return rewritePayload(event.payload, ctx, config);
  });

  pi.registerCommand(COMMAND_NAME, {
    description: "Show or reload OpenRouter controls",
    handler: async (args, ctx) => {
      const action = args.trim().toLowerCase();
      if (!action || action === "status") {
        ctx.ui.notify(formatStatus(config, ctx.cwd), "info");
        return;
      }

      if (action === "reload") {
        config = loadConfig(ctx.cwd);
        updateOpenRouterControlsStatus(ctx, config);
        ctx.ui.notify("OpenRouter controls reloaded", "info");
        return;
      }

      ctx.ui.notify(`Usage: /${COMMAND_NAME} status | reload`, "error");
    },
  });
}

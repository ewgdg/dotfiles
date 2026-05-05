import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "@mariozechner/pi-coding-agent";

type WebSearchMode = "cached" | "live" | "disabled";
type WebSearchContextSize = "low" | "medium" | "high";
type JsonRecord = Record<string, unknown>;

interface OpenAINativeWebSearchUserLocation {
  type: "approximate";
  country?: string;
  region?: string;
  city?: string;
  timezone?: string;
}

interface OpenAINativeWebSearchTool {
  type: "web_search";
  external_web_access: boolean;
  filters?: { allowed_domains?: string[] };
  user_location?: OpenAINativeWebSearchUserLocation;
  search_context_size?: WebSearchContextSize;
  search_content_types?: string[];
}

interface OpenAINativeWebSearchConfig {
  mode: WebSearchMode;
  allowedDomains?: string[];
  searchContextSize?: WebSearchContextSize;
  userLocation?: OpenAINativeWebSearchUserLocation;
  searchContentTypes?: string[];
}

const WEB_SEARCH_TOOL_NAME = "web_search";
const STATUS_KEY = "pi-openai-native-web-search";
const CONFIG_FILE_NAME = "pi-openai-native-web-search.json";
const WEB_SEARCH_MODE_OPTIONS = ["live", "cached", "disabled"] as const satisfies readonly WebSearchMode[];

const EMPTY_PARAMETERS_SCHEMA = {
  type: "object",
  additionalProperties: false,
} as const;

interface ExtensionState {
  mode: WebSearchMode;
}

function parseMode(value: string | undefined): WebSearchMode {
  switch (value?.trim().toLowerCase()) {
    case "disabled":
    case "off":
    case "false":
    case "0":
      return "disabled";
    case "cached":
      return "cached";
    case "live":
    case "true":
    case "1":
      return "live";
    default:
      return "live";
  }
}

function loadOpenAINativeWebSearchConfig(cwd: string = process.cwd()): OpenAINativeWebSearchConfig {
  const globalConfig = readConfigFile(join(getAgentDir(), CONFIG_FILE_NAME));
  const projectConfig = readConfigFile(join(cwd, ".pi", CONFIG_FILE_NAME));
  return normalizeConfig(mergeConfig(globalConfig, projectConfig));
}

function getAgentDir(): string {
  const configuredAgentDir = process.env.PI_CODING_AGENT_DIR?.trim();
  return configuredAgentDir || join(homedir(), ".pi", "agent");
}

function readConfigFile(path: string): Partial<OpenAINativeWebSearchConfig> {
  if (!existsSync(path)) return {};

  const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
  if (!isRecord(parsed)) {
    throw new Error(`Expected ${path} to contain a JSON object`);
  }
  return parsed as Partial<OpenAINativeWebSearchConfig>;
}

function mergeConfig(
  base: Partial<OpenAINativeWebSearchConfig>,
  override: Partial<OpenAINativeWebSearchConfig>
): Partial<OpenAINativeWebSearchConfig> {
  return {
    ...base,
    ...override,
    userLocation: mergeUserLocation(base.userLocation, override.userLocation),
  };
}

function mergeUserLocation(
  base: OpenAINativeWebSearchConfig["userLocation"],
  override: OpenAINativeWebSearchConfig["userLocation"]
): OpenAINativeWebSearchConfig["userLocation"] {
  if (!base && !override) return undefined;
  return normalizeUserLocation({ ...(isRecord(base) ? base : {}), ...(isRecord(override) ? override : {}) });
}

function normalizeConfig(config: Partial<OpenAINativeWebSearchConfig>): OpenAINativeWebSearchConfig {
  const allowedDomains = normalizeStringArray(config.allowedDomains);
  const searchContextSize = parseContextSize(config.searchContextSize);
  const userLocation = normalizeUserLocation(config.userLocation);
  const searchContentTypes = normalizeStringArray(config.searchContentTypes);

  return {
    mode: parseMode(typeof config.mode === "string" ? config.mode : undefined),
    ...(allowedDomains ? { allowedDomains } : {}),
    ...(searchContextSize ? { searchContextSize } : {}),
    ...(userLocation ? { userLocation } : {}),
    ...(searchContentTypes ? { searchContentTypes } : {}),
  };
}

function parseContextSize(value: unknown): WebSearchContextSize | undefined {
  if (value === "low" || value === "medium" || value === "high") return value;
  return undefined;
}

function normalizeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = value.map((item) => (typeof item === "string" ? item.trim() : "")).filter(Boolean);
  return items.length > 0 ? items : undefined;
}

function normalizeUserLocation(value: unknown): OpenAINativeWebSearchUserLocation | undefined {
  if (!isRecord(value)) return undefined;

  const location: OpenAINativeWebSearchUserLocation = { type: "approximate" };
  for (const key of ["country", "region", "city", "timezone"] as const) {
    const field = value[key];
    if (typeof field === "string" && field.trim()) {
      location[key] = field.trim();
    }
  }

  return Object.keys(location).length > 1 ? location : undefined;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isOpenAICodexModel(model: ExtensionContext["model"]): boolean {
  return (model?.provider ?? "").toLowerCase() === "openai-codex";
}

function supportsTextAndImageSearch(model: ExtensionContext["model"]): boolean {
  // Mirrors pi-codex-conversion: Spark lacks multimodal OpenAI native web search.
  return isOpenAICodexModel(model) && !(model?.id ?? "").toLowerCase().includes("spark");
}

function isFunctionWebSearchTool(tool: unknown): boolean {
  return isRecord(tool) && tool.type === "function" && tool.name === WEB_SEARCH_TOOL_NAME;
}

function isOpenAINativeWebSearchTool(tool: unknown): boolean {
  return isRecord(tool) && (tool.type === "web_search" || tool.type === "web_search_preview");
}

function buildOpenAINativeWebSearchTool(
  mode: Exclude<WebSearchMode, "disabled">,
  model: ExtensionContext["model"],
  config: OpenAINativeWebSearchConfig
): OpenAINativeWebSearchTool {
  const defaultContentTypes = supportsTextAndImageSearch(model) ? ["text", "image"] : undefined;

  return {
    type: "web_search",
    external_web_access: mode === "live",
    ...(config.allowedDomains ? { filters: { allowed_domains: config.allowedDomains } } : {}),
    ...(config.userLocation ? { user_location: config.userLocation } : {}),
    ...(config.searchContextSize ? { search_context_size: config.searchContextSize } : {}),
    ...(config.searchContentTypes
      ? { search_content_types: config.searchContentTypes }
      : defaultContentTypes
        ? { search_content_types: defaultContentTypes }
        : {}),
  };
}

function rewriteOpenAINativeWebSearchTools(
  payload: unknown,
  mode: WebSearchMode,
  model: ExtensionContext["model"],
  config: OpenAINativeWebSearchConfig
): unknown {
  if (!isOpenAICodexModel(model) || !isRecord(payload) || !Array.isArray(payload.tools)) {
    return undefined;
  }

  let changed = false;
  const nextTools: unknown[] = [];

  for (const tool of payload.tools) {
    if (!isFunctionWebSearchTool(tool) && !isOpenAINativeWebSearchTool(tool)) {
      nextTools.push(tool);
      continue;
    }

    changed = true;
    if (mode !== "disabled") {
      // Codex source sends a provider-native Responses API tool, not a function
      // tool. Pi first serializes active tools as functions, so we rewrite here.
      nextTools.push(buildOpenAINativeWebSearchTool(mode, model, config));
    }
  }

  return changed ? { ...payload, tools: nextTools } : undefined;
}

function createWebSearchTool(): ToolDefinition<typeof EMPTY_PARAMETERS_SCHEMA> {
  return {
    name: WEB_SEARCH_TOOL_NAME,
    label: WEB_SEARCH_TOOL_NAME,
    description:
      "Search the web for sources relevant to the current task. Uses OpenAI native web search; currently supports openai-codex and does not execute locally.",
    promptSnippet:
      "Search the web for sources relevant to the current task. Use web_search when you need up-to-date information, external references, or broader context beyond the workspace.",
    parameters: EMPTY_PARAMETERS_SCHEMA,
    prepareArguments: () => ({}),
    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      if (!isOpenAICodexModel(ctx.model)) {
        throw new Error("web_search is only available with the openai-codex provider");
      }
      throw new Error("web_search is a native openai-codex provider tool and should not execute locally");
    },
  };
}

function syncActiveWebSearchTool(pi: ExtensionAPI, ctx: ExtensionContext, state: ExtensionState): void {
  const activeTools = pi.getActiveTools();
  const shouldEnable = state.mode !== "disabled" && isOpenAICodexModel(ctx.model);
  const isActive = activeTools.includes(WEB_SEARCH_TOOL_NAME);

  if (shouldEnable && !isActive) {
    pi.setActiveTools([...activeTools, WEB_SEARCH_TOOL_NAME]);
  } else if (!shouldEnable && isActive) {
    pi.setActiveTools(activeTools.filter((toolName) => toolName !== WEB_SEARCH_TOOL_NAME));
  }

  if (ctx.hasUI) {
    ctx.ui.setStatus(STATUS_KEY, shouldEnable ? formatStatus(ctx, state.mode) : undefined);
  }
}

function formatStatus(ctx: ExtensionContext, mode: WebSearchMode): string | undefined {
  switch (mode) {
    case "live":
      return ctx.ui.theme.fg("success", "🌐live");
    case "cached":
      return ctx.ui.theme.fg("warning", "🌐cached");
    case "disabled":
      return undefined;
  }
}

function setMode(state: ExtensionState, mode: WebSearchMode): void {
  state.mode = mode;
}

export default function openAINativeWebSearch(pi: ExtensionAPI) {
  let config = loadOpenAINativeWebSearchConfig();
  const state: ExtensionState = {
    mode: config.mode,
  };

  pi.registerTool(createWebSearchTool());

  pi.on("session_start", async (_event, ctx) => {
    config = loadOpenAINativeWebSearchConfig(ctx.cwd);
    setMode(state, config.mode);
    syncActiveWebSearchTool(pi, ctx, state);
  });

  pi.on("model_select", async (_event, ctx) => {
    syncActiveWebSearchTool(pi, ctx, state);
  });

  pi.on("before_provider_request", async (event, ctx) => {
    return rewriteOpenAINativeWebSearchTools(event.payload, state.mode, ctx.model, config);
  });

  pi.registerCommand("openai-native-web-search", {
    description: "Show or set OpenAI native web search mode: live, cached, disabled",
    getArgumentCompletions: (prefix: string) => {
      const normalizedPrefix = prefix.trim().toLowerCase();
      const items = WEB_SEARCH_MODE_OPTIONS.map((mode) => ({ value: mode, label: mode }));
      const filteredItems = items.filter((item) => item.value.startsWith(normalizedPrefix));
      return filteredItems.length > 0 ? filteredItems : null;
    },
    handler: async (args, ctx) => {
      const trimmedArgs = args.trim();
      const selectedMode = trimmedArgs || (await ctx.ui.select("OpenAI native web search", [...WEB_SEARCH_MODE_OPTIONS]));

      if (!selectedMode) {
        ctx.ui.notify(`OpenAI native web search unchanged: ${state.mode}`, "info");
        return;
      }

      setMode(state, parseMode(selectedMode));
      syncActiveWebSearchTool(pi, ctx, state);

      ctx.ui.notify(`OpenAI native web search: ${state.mode} (session only; edit config file to persist)`, "info");
    },
  });
}

import type { ToolDefinition } from "@earendil-works/pi-coding-agent";
import { isOpenAICodexModel, supportsTextAndImageSearch } from "./model";
import type {
  CurrentModel,
  OpenAINativeWebSearchTool,
  WebSearchConfig,
  WebSearchMode,
} from "./types";
import { isRecord } from "./types";

export const WEB_SEARCH_TOOL_NAME = "web_search";
export const WEB_SEARCH_MODE_OPTIONS = ["live", "cached", "disabled"] as const satisfies readonly WebSearchMode[];

const EMPTY_PARAMETERS_SCHEMA = {
  type: "object",
  additionalProperties: false,
} as const;

export function shouldEnableWebSearch(mode: WebSearchMode, model: CurrentModel): boolean {
  return mode !== "disabled" && isOpenAICodexModel(model);
}

export function createWebSearchTool(): ToolDefinition<typeof EMPTY_PARAMETERS_SCHEMA> {
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

export function rewriteOpenAINativeWebSearchTools(
  payload: unknown,
  mode: WebSearchMode,
  model: CurrentModel,
  config: WebSearchConfig,
): unknown {
  if (!isRecord(payload) || !Array.isArray(payload.tools)) {
    return undefined;
  }

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
      // Codex expects a provider-native Responses API tool, not a function tool.
      // Pi serializes active tools as functions first, so rewrite at payload edge.
      nextTools.push(buildOpenAINativeWebSearchTool(mode, model, config));
    }
  }

  return changed ? { ...payload, tools: nextTools } : undefined;
}

function isFunctionWebSearchTool(tool: unknown): boolean {
  return isRecord(tool) && tool.type === "function" && tool.name === WEB_SEARCH_TOOL_NAME;
}

function isOpenAINativeWebSearchTool(tool: unknown): boolean {
  return isRecord(tool) && (tool.type === "web_search" || tool.type === "web_search_preview");
}

function buildOpenAINativeWebSearchTool(
  mode: Exclude<WebSearchMode, "disabled">,
  model: CurrentModel,
  config: WebSearchConfig,
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


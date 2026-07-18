import { isOpenAICodexModel, supportsTextAndImageSearch } from "./model";
import type {
  CurrentModel,
  OpenAINativeWebSearchTool,
  WebSearchConfig,
  WebSearchMode,
} from "./types";
import { isRecord } from "./types";

export const WEB_SEARCH_MODE_OPTIONS = ["live", "cached", "disabled"] as const satisfies readonly WebSearchMode[];

const INTERNAL_CITATION_TAG_PATTERN = /cite((?:[^]+)+)/gu;

export function shouldEnableWebSearch(mode: WebSearchMode, model: CurrentModel): boolean {
  return mode !== "disabled" && isOpenAICodexModel(model);
}

export function rewriteInternalCitationTags(text: string): string | undefined {
  if (!INTERNAL_CITATION_TAG_PATTERN.test(text)) return undefined;
  INTERNAL_CITATION_TAG_PATTERN.lastIndex = 0;
  return text.replace(INTERNAL_CITATION_TAG_PATTERN, (_tag, references: string) => {
    const sourceCount = references.split("").filter(Boolean).length;
    return sourceCount > 1 ? `(${sourceCount} web sources)` : "(web source)";
  });
}

export function rewriteOpenAINativeWebSearchTools(
  payload: unknown,
  mode: WebSearchMode,
  model: CurrentModel,
  config: WebSearchConfig,
): unknown {
  if (!isOpenAICodexModel(model) || !isRecord(payload)) {
    return undefined;
  }

  if (payload.tools !== undefined && !Array.isArray(payload.tools)) {
    return undefined;
  }

  const tools = payload.tools ?? [];
  const toolsWithoutWebSearch = tools.filter((tool) => !isOpenAINativeWebSearchTool(tool));

  if (mode === "disabled") {
    return toolsWithoutWebSearch.length === tools.length
      ? undefined
      : { ...payload, tools: toolsWithoutWebSearch };
  }

  // Provider-native capabilities belong at the provider payload seam, not in Pi's local tool registry.
  return {
    ...payload,
    tools: [...toolsWithoutWebSearch, buildOpenAINativeWebSearchTool(mode, model, config)],
  };
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


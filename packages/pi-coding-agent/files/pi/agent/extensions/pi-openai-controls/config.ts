import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { parseServiceTier } from "./service-tier";
import type {
  OpenAIControlsConfig,
  OpenAIControlsState,
  OpenAINativeWebSearchUserLocation,
  ServiceTier,
  WebSearchConfig,
  WebSearchContextSize,
  WebSearchMode,
} from "./types";
import { isRecord, type JsonRecord } from "./types";

export const CONFIG_FILE_NAME = "pi-openai-controls.json";

const WEB_SEARCH_MODE_ALIASES: Record<string, WebSearchMode> = {
  disabled: "disabled",
  off: "disabled",
  false: "disabled",
  "0": "disabled",
  cached: "cached",
  live: "live",
  true: "live",
  "1": "live",
};

interface PartialOpenAIControlsConfig {
  webSearch?: Partial<WebSearchConfig>;
  serviceTier?: ServiceTier;
}

export function parseWebSearchMode(value: string | undefined): WebSearchMode {
  const normalized = value?.trim().toLowerCase() ?? "";
  return WEB_SEARCH_MODE_ALIASES[normalized] ?? "live";
}

export function loadOpenAIControlsConfig(cwd: string = process.cwd()): OpenAIControlsConfig {
  const globalConfig = readConfigFile(join(getAgentDir(), CONFIG_FILE_NAME));
  const projectConfig = readConfigFile(join(cwd, ".pi", CONFIG_FILE_NAME));
  return normalizeConfig(mergePartialConfig(globalConfig, projectConfig));
}

export function getConfigSearchPaths(cwd: string): string[] {
  return [join(getAgentDir(), CONFIG_FILE_NAME), join(cwd, ".pi", CONFIG_FILE_NAME)];
}

export function getWritableConfigPath(cwd: string): string {
  const projectConfigPath = join(cwd, ".pi", CONFIG_FILE_NAME);
  return existsSync(projectConfigPath) ? projectConfigPath : join(getAgentDir(), CONFIG_FILE_NAME);
}

export function saveOpenAIControlsStateToConfig(cwd: string, state: OpenAIControlsState): string {
  const configPath = getWritableConfigPath(cwd);
  const raw = readJsonObjectFile(configPath);
  const webSearch = isRecord(raw.web_search) ? raw.web_search : {};
  const serviceTier = isRecord(raw.service_tier) ? raw.service_tier : {};

  raw.web_search = { ...webSearch, mode: state.webSearchMode };
  raw.service_tier = { ...serviceTier, default: state.serviceTier };

  mkdirSync(dirname(configPath), { recursive: true });
  writeFileSync(configPath, `${JSON.stringify(raw, null, 2)}\n`, "utf8");
  return configPath;
}

function getAgentDir(): string {
  const configuredAgentDir = process.env.PI_CODING_AGENT_DIR?.trim();
  return configuredAgentDir || join(homedir(), ".pi", "agent");
}

function readConfigFile(path: string): PartialOpenAIControlsConfig {
  if (!existsSync(path)) return {};
  return parseRawConfig(readJsonObjectFile(path), path);
}

function readJsonObjectFile(path: string): JsonRecord {
  if (!existsSync(path)) return {};

  const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
  if (!isRecord(parsed)) {
    throw new Error(`Expected ${path} to contain a JSON object`);
  }
  return parsed;
}

function parseRawConfig(raw: JsonRecord, path: string): PartialOpenAIControlsConfig {
  const webSearch = isRecord(raw.web_search) ? parseWebSearchConfig(raw.web_search, `${path}.web_search`) : undefined;
  const serviceTier = isRecord(raw.service_tier)
    ? parseServiceTierConfig(raw.service_tier, `${path}.service_tier`)
    : undefined;
  return {
    ...(webSearch ? { webSearch } : {}),
    ...(serviceTier ? { serviceTier } : {}),
  };
}

function parseWebSearchConfig(raw: JsonRecord, context: string): Partial<WebSearchConfig> {
  const mode = raw.mode === undefined ? undefined : parseRequiredWebSearchMode(raw.mode, `${context}.mode`);
  const allowedDomains = parseOptionalStringArray(raw.allowed_domains, `${context}.allowed_domains`);
  const searchContextSize = parseOptionalEnum(raw.search_context_size, new Set(["low", "medium", "high"] as const), `${context}.search_context_size`);
  const searchContentTypes = parseOptionalStringArray(raw.search_content_types, `${context}.search_content_types`);
  const userLocation = parseUserLocation(raw.user_location, `${context}.user_location`);

  return {
    ...(mode ? { mode } : {}),
    ...(allowedDomains ? { allowedDomains } : {}),
    ...(searchContextSize ? { searchContextSize } : {}),
    ...(searchContentTypes ? { searchContentTypes } : {}),
    ...(userLocation ? { userLocation } : {}),
  };
}

function parseServiceTierConfig(raw: JsonRecord, context: string): ServiceTier | undefined {
  if (raw.default === undefined) return undefined;
  if (typeof raw.default !== "string") throw new Error(`${context}.default must be a string`);
  const serviceTier = parseServiceTier(raw.default);
  if (!serviceTier) throw new Error(`${context}.default must be auto, default, flex, or priority`);
  return serviceTier;
}

function parseRequiredWebSearchMode(value: unknown, context: string): WebSearchMode {
  if (typeof value !== "string") throw new Error(`${context} must be a string`);
  const mode = WEB_SEARCH_MODE_ALIASES[value.trim().toLowerCase()];
  if (!mode) throw new Error(`${context} must be live, cached, or disabled`);
  return mode;
}

function parseOptionalEnum<T extends string>(value: unknown, allowed: Set<T>, context: string): T | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string") throw new Error(`${context} must be a string`);
  const normalized = value.trim().toLowerCase() as T;
  if (!allowed.has(normalized)) {
    throw new Error(`${context} must be one of: ${[...allowed].join(", ")}`);
  }
  return normalized;
}

function parseOptionalStringArray(value: unknown, context: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw new Error(`${context} must be an array of strings`);
  const items = value.map((item, index) => {
    if (typeof item !== "string") throw new Error(`${context}[${index}] must be a string`);
    return item.trim();
  }).filter(Boolean);
  return items.length > 0 ? items : undefined;
}

function parseUserLocation(value: unknown, context: string): OpenAINativeWebSearchUserLocation | undefined {
  if (value === undefined) return undefined;
  if (!isRecord(value)) throw new Error(`${context} must be a JSON object`);

  const location: OpenAINativeWebSearchUserLocation = { type: "approximate" };
  for (const key of ["country", "region", "city", "timezone"] as const) {
    const field = value[key];
    if (field === undefined) continue;
    if (typeof field !== "string") throw new Error(`${context}.${key} must be a string`);
    if (field.trim()) location[key] = field.trim();
  }

  return Object.keys(location).length > 1 ? location : undefined;
}

function mergePartialConfig(
  base: PartialOpenAIControlsConfig,
  override: PartialOpenAIControlsConfig,
): PartialOpenAIControlsConfig {
  return {
    webSearch: mergeWebSearchConfig(base.webSearch, override.webSearch),
    serviceTier: override.serviceTier ?? base.serviceTier,
  };
}

function mergeWebSearchConfig(
  base: Partial<WebSearchConfig> | undefined,
  override: Partial<WebSearchConfig> | undefined,
): Partial<WebSearchConfig> | undefined {
  if (!base && !override) return undefined;
  return {
    ...base,
    ...override,
    userLocation: mergeUserLocation(base?.userLocation, override?.userLocation),
  };
}

function mergeUserLocation(
  base: OpenAINativeWebSearchUserLocation | undefined,
  override: OpenAINativeWebSearchUserLocation | undefined,
): OpenAINativeWebSearchUserLocation | undefined {
  if (!base && !override) return undefined;
  const merged = { ...(base ?? { type: "approximate" as const }), ...(override ?? {}) };
  return Object.keys(merged).length > 1 ? merged : undefined;
}

function normalizeConfig(config: PartialOpenAIControlsConfig): OpenAIControlsConfig {
  return {
    webSearch: {
      mode: config.webSearch?.mode ?? "live",
      ...(config.webSearch?.allowedDomains ? { allowedDomains: config.webSearch.allowedDomains } : {}),
      ...(config.webSearch?.searchContextSize ? { searchContextSize: config.webSearch.searchContextSize } : {}),
      ...(config.webSearch?.searchContentTypes ? { searchContentTypes: config.webSearch.searchContentTypes } : {}),
      ...(config.webSearch?.userLocation ? { userLocation: config.webSearch.userLocation } : {}),
    },
    serviceTier: config.serviceTier ?? "auto",
  };
}

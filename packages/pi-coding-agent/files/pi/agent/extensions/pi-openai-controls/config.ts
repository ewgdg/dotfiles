import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { CONFIG_DIR_NAME, getAgentDir } from "@earendil-works/pi-coding-agent";
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

export const SETTINGS_KEY = "pi-openai-controls";
const SETTINGS_FILE = "settings.json";

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

export function loadOpenAIControlsConfig(
  cwd: string = process.cwd(),
  projectTrusted = false,
): OpenAIControlsConfig {
  const globalConfig = readSettingsConfig(globalSettingsPath());
  const projectConfig = projectTrusted
    ? readSettingsConfig(projectSettingsPath(cwd))
    : {};
  return normalizeConfig(mergePartialConfig(globalConfig, projectConfig));
}

export function getSettingsSearchPaths(cwd: string, projectTrusted: boolean): string[] {
  return projectTrusted
    ? [globalSettingsPath(), projectSettingsPath(cwd)]
    : [globalSettingsPath()];
}

export function getWritableSettingsPath(cwd: string, projectTrusted: boolean): string {
  const projectPath = projectSettingsPath(cwd);
  return projectTrusted && hasSettingsNamespace(projectPath)
    ? projectPath
    : globalSettingsPath();
}

export function saveOpenAIControlsStateToSettings(
  cwd: string,
  projectTrusted: boolean,
  state: OpenAIControlsState,
): string {
  const settingsPath = getWritableSettingsPath(cwd, projectTrusted);
  const settings = readJsonObjectFile(settingsPath);
  const configuredNamespace = settings[SETTINGS_KEY];
  if (configuredNamespace !== undefined && !isRecord(configuredNamespace)) {
    throw new Error(`${settingsPath}.${SETTINGS_KEY} must be a JSON object`);
  }
  const namespace = configuredNamespace ?? {};
  const webSearch = isRecord(namespace.web_search) ? namespace.web_search : {};
  const serviceTier = isRecord(namespace.service_tier) ? namespace.service_tier : {};

  namespace.web_search = { ...webSearch, mode: state.webSearchMode };
  namespace.service_tier = { ...serviceTier, default: state.serviceTier };
  settings[SETTINGS_KEY] = namespace;

  mkdirSync(dirname(settingsPath), { recursive: true });
  writeFileSync(settingsPath, `${JSON.stringify(settings, null, 2)}\n`, "utf8");
  return settingsPath;
}

function globalSettingsPath(): string {
  return join(getAgentDir(), SETTINGS_FILE);
}

function projectSettingsPath(cwd: string): string {
  return join(cwd, CONFIG_DIR_NAME, SETTINGS_FILE);
}

function hasSettingsNamespace(path: string): boolean {
  if (!existsSync(path)) return false;
  return Object.hasOwn(readJsonObjectFile(path), SETTINGS_KEY);
}

function readSettingsConfig(path: string): PartialOpenAIControlsConfig {
  if (!existsSync(path)) return {};
  const settings = readJsonObjectFile(path);
  const namespace = settings[SETTINGS_KEY];
  if (namespace === undefined) return {};
  if (!isRecord(namespace)) {
    throw new Error(`${path}.${SETTINGS_KEY} must be a JSON object`);
  }
  return parseRawConfig(namespace, `${path}.${SETTINGS_KEY}`);
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

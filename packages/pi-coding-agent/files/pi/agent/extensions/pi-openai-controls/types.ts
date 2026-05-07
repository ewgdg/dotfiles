import type { ExtensionContext } from "@earendil-works/pi-coding-agent";

export type JsonRecord = Record<string, unknown>;
export type WebSearchMode = "cached" | "live" | "disabled";
export type WebSearchContextSize = "low" | "medium" | "high";
export type ServiceTier = "auto" | "default" | "flex" | "priority";

export interface OpenAINativeWebSearchUserLocation {
  type: "approximate";
  country?: string;
  region?: string;
  city?: string;
  timezone?: string;
}

export interface OpenAINativeWebSearchTool {
  type: "web_search";
  external_web_access: boolean;
  filters?: { allowed_domains?: string[] };
  user_location?: OpenAINativeWebSearchUserLocation;
  search_context_size?: WebSearchContextSize;
  search_content_types?: string[];
}

export interface WebSearchConfig {
  mode: WebSearchMode;
  allowedDomains?: string[];
  searchContextSize?: WebSearchContextSize;
  userLocation?: OpenAINativeWebSearchUserLocation;
  searchContentTypes?: string[];
}

export interface OpenAIControlsConfig {
  webSearch: WebSearchConfig;
  serviceTier: ServiceTier;
}

export interface OpenAIControlsState {
  webSearchMode: WebSearchMode;
  serviceTier: ServiceTier;
}

export type CurrentModel = ExtensionContext["model"];

export function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

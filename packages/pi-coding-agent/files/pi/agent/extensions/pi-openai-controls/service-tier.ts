import { isOpenAICodexModel, isOpenAIResponsesPayloadModel } from "./model";
import type { CurrentModel, ServiceTier } from "./types";
import { isRecord } from "./types";

export const SERVICE_TIER_SYMBOL = "🚀";
export const SERVICE_TIER_OPTIONS = ["auto", "default", "flex", "priority"] as const satisfies readonly ServiceTier[];

export function parseServiceTier(value: string | undefined): ServiceTier | undefined {
  switch (value?.trim().toLowerCase()) {
    case "auto":
      return "auto";
    case "default":
    case "standard":
    case "std":
      return "default";
    case "flex":
      return "flex";
    case "priority":
    case "prio":
      return "priority";
    default:
      return undefined;
  }
}

export function rewriteOpenAIServiceTier(
  payload: unknown,
  serviceTier: ServiceTier,
  model: CurrentModel
): unknown {
  const providerServiceTier = getSupportedProviderServiceTier(serviceTier, model);
  if (!isOpenAIResponsesPayloadModel(model) || !isRecord(payload) || providerServiceTier === undefined || payload.service_tier === providerServiceTier) {
    return undefined;
  }

  return { ...payload, service_tier: providerServiceTier };
}

export function getSupportedProviderServiceTier(serviceTier: ServiceTier, model: CurrentModel): ServiceTier | undefined {
  if (isOpenAICodexModel(model)) {
    // Pi's openai-codex provider uses ChatGPT's Codex backend, not the public
    // Responses API. That backend rejects explicit "default" and "flex" today;
    // omit service_tier for normal/default behavior and only send priority.
    return serviceTier === "priority" ? "priority" : undefined;
  }

  return serviceTier;
}

export function formatServiceTierStatus(serviceTier: ServiceTier): string | undefined {
  switch (serviceTier) {
    case "auto":
      return undefined;
    case "default":
      return `${SERVICE_TIER_SYMBOL}std`;
    case "flex":
      return `${SERVICE_TIER_SYMBOL}flex`;
    case "priority":
      return `${SERVICE_TIER_SYMBOL}prio`;
  }
}

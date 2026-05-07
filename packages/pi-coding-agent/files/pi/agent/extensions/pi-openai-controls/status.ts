import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { formatServiceTierStatus, getSupportedProviderServiceTier } from "./service-tier";
import { isOpenAIResponsesPayloadModel } from "./model";
import type { OpenAIControlsConfig, OpenAIControlsState, ServiceTier } from "./types";
import { shouldEnableWebSearch } from "./web-search";

// Separate keys keep footer items from visually merging; pi sorts statuses by key.
export const WEB_SEARCH_STATUS_KEY = "00-openai-web-search";
export const SERVICE_TIER_STATUS_KEY = "01-openai-service-tier";

export function updateOpenAIControlsStatus(
  ctx: ExtensionContext,
  state: OpenAIControlsState,
  _config: OpenAIControlsConfig
): void {
  if (!ctx.hasUI) return;

  ctx.ui.setStatus(
    WEB_SEARCH_STATUS_KEY,
    shouldEnableWebSearch(state.webSearchMode, ctx.model) ? formatWebSearchStatus(ctx, state.webSearchMode) : undefined
  );

  const providerServiceTier = getSupportedProviderServiceTier(state.serviceTier, ctx.model);
  const serviceTierStatus = providerServiceTier ? formatServiceTierStatus(providerServiceTier) : undefined;
  ctx.ui.setStatus(
    SERVICE_TIER_STATUS_KEY,
    serviceTierStatus && isOpenAIResponsesPayloadModel(ctx.model)
      ? formatServiceTierStatusWithColor(ctx, providerServiceTier!, serviceTierStatus)
      : undefined
  );
}

function formatWebSearchStatus(ctx: ExtensionContext, mode: OpenAIControlsState["webSearchMode"]): string {
  switch (mode) {
    case "live":
      return ctx.ui.theme.fg("success", "🌐live");
    case "cached":
      return ctx.ui.theme.fg("warning", "🌐cached");
    case "disabled":
      return "";
  }
}

function formatServiceTierStatusWithColor(ctx: ExtensionContext, serviceTier: ServiceTier, status: string): string {
  switch (serviceTier) {
    case "auto":
      return "";
    case "default":
      return ctx.ui.theme.fg("muted", status);
    case "flex":
      return ctx.ui.theme.fg("warning", status);
    case "priority":
      return ctx.ui.theme.fg("success", status);
  }
}

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  getSettingsSearchPaths,
  loadOpenAIControlsConfig,
  parseWebSearchMode,
  saveOpenAIControlsStateToSettings,
} from "./config";
import {
  getSupportedProviderServiceTier,
  parseServiceTier,
  rewriteOpenAIServiceTier,
  SERVICE_TIER_OPTIONS,
} from "./service-tier";
import type { OpenAIControlsConfig, OpenAIControlsState, ServiceTier, WebSearchMode } from "./types";
import { updateOpenAIControlsStatus } from "./status";
import {
  createWebSearchTool,
  rewriteInternalCitationTags,
  rewriteOpenAINativeWebSearchTools,
  rewriteWebSearchCitationInstructions,
  shouldEnableWebSearch,
  WEB_SEARCH_MODE_OPTIONS,
  WEB_SEARCH_TOOL_NAME,
} from "./web-search";

const COMMAND_NAME = "openai-controls";
const SUBCOMMANDS = ["status", "reload", "service-tier", "web-search"] as const;

type OpenAIControlsAction = "status" | "reload" | "service-tier" | "web-search";

function createState(config: OpenAIControlsConfig): OpenAIControlsState {
  return {
    webSearchMode: config.webSearch.mode,
    serviceTier: config.serviceTier,
  };
}

function resetStateFromConfig(state: OpenAIControlsState, config: OpenAIControlsConfig): void {
  state.webSearchMode = config.webSearch.mode;
  state.serviceTier = config.serviceTier;
}

function syncActiveWebSearchTool(
  pi: ExtensionAPI,
  ctx: ExtensionContext,
  state: OpenAIControlsState,
  config: OpenAIControlsConfig
): void {
  const activeTools = pi.getActiveTools();
  const shouldEnable = shouldEnableWebSearch(state.webSearchMode, ctx.model);
  const isActive = activeTools.includes(WEB_SEARCH_TOOL_NAME);

  if (shouldEnable && !isActive) {
    pi.setActiveTools([...activeTools, WEB_SEARCH_TOOL_NAME]);
  } else if (!shouldEnable && isActive) {
    pi.setActiveTools(activeTools.filter((toolName) => toolName !== WEB_SEARCH_TOOL_NAME));
  }

  updateOpenAIControlsStatus(ctx, state, config);
}

function rewritePayload(
  payload: unknown,
  ctx: ExtensionContext,
  state: OpenAIControlsState,
  config: OpenAIControlsConfig
): unknown {
  const serviceTierPayload = rewriteOpenAIServiceTier(payload, state.serviceTier, ctx.model);
  const payloadAfterServiceTier = serviceTierPayload ?? payload;
  const webSearchPayload = rewriteOpenAINativeWebSearchTools(
    payloadAfterServiceTier,
    state.webSearchMode,
    ctx.model,
    config.webSearch
  );

  const payloadAfterWebSearch = webSearchPayload ?? payloadAfterServiceTier;
  const citationPayload = rewriteWebSearchCitationInstructions(
    payloadAfterWebSearch,
    state.webSearchMode,
    ctx.model,
  );

  return citationPayload ?? webSearchPayload ?? serviceTierPayload;
}

function getCommandCandidates(): string[] {
  return [
    "status",
    "reload",
    ...SERVICE_TIER_OPTIONS.map((serviceTier) => `service-tier ${serviceTier}`),
    ...WEB_SEARCH_MODE_OPTIONS.map((mode) => `web-search ${mode}`),
  ];
}

function getCommandCompletions(prefix: string) {
  const normalizedPrefix = prefix.trimStart().toLowerCase();
  const candidates = getCommandCandidates().map((value) => ({ value, label: value }));
  const filteredItems = candidates.filter((item) => item.value.startsWith(normalizedPrefix));
  return filteredItems.length > 0 ? filteredItems : null;
}

function parseCommand(args: string): { action: OpenAIControlsAction; value?: string } | undefined {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return undefined;
  const action = parts[0] as OpenAIControlsAction;
  if (!SUBCOMMANDS.includes(action)) return undefined;
  return { action, value: parts.slice(1).join(" ") || undefined };
}

async function selectCommandArgs(ctx: ExtensionContext): Promise<string | undefined> {
  if (!ctx.hasUI) return "status";
  return ctx.ui.select("OpenAI controls", getCommandCandidates());
}

async function selectServiceTier(ctx: ExtensionContext): Promise<ServiceTier | undefined> {
  if (!ctx.hasUI) return undefined;
  const selected = await ctx.ui.select("OpenAI service tier", [...SERVICE_TIER_OPTIONS]);
  return parseServiceTier(selected);
}

async function selectWebSearchMode(ctx: ExtensionContext): Promise<WebSearchMode | undefined> {
  if (!ctx.hasUI) return undefined;
  return ctx.ui.select("OpenAI native web search", [...WEB_SEARCH_MODE_OPTIONS]);
}

function parseWebSearchCommandMode(value: string | undefined): WebSearchMode | undefined {
  const normalized = value?.trim().toLowerCase();
  if (!normalized) return undefined;
  if (["live", "cached", "disabled", "off", "false", "0", "true", "1"].includes(normalized)) {
    return parseWebSearchMode(normalized);
  }
  return undefined;
}

function formatStatusMessage(
  state: OpenAIControlsState,
  _config: OpenAIControlsConfig,
  ctx: ExtensionContext,
): string {
  const settingsPaths = getSettingsSearchPaths(ctx.cwd, ctx.isProjectTrusted()).join(", ");
  return [
    `OpenAI controls: service-tier=${state.serviceTier}, web-search=${state.webSearchMode}`,
    `Settings: ${settingsPaths}`,
  ].join("\n");
}

export default function openAIControls(pi: ExtensionAPI) {
  let config = loadOpenAIControlsConfig();
  const state = createState(config);

  pi.registerTool(createWebSearchTool());

  pi.on("session_start", async (_event, ctx) => {
    config = loadOpenAIControlsConfig(ctx.cwd, ctx.isProjectTrusted());
    resetStateFromConfig(state, config);
    syncActiveWebSearchTool(pi, ctx, state, config);
  });

  pi.on("model_select", async (_event, ctx) => {
    syncActiveWebSearchTool(pi, ctx, state, config);
  });

  pi.on("before_provider_request", async (event, ctx) => {
    return rewritePayload(event.payload, ctx, state, config);
  });

  pi.on("message_end", async (event) => {
    if (event.message.role !== "assistant") return;

    let changed = false;
    const content = event.message.content.map((block) => {
      if (block.type !== "text") return block;
      const text = rewriteInternalCitationTags(block.text);
      if (text === undefined) return block;
      changed = true;
      return { ...block, text };
    });

    if (changed) return { message: { ...event.message, content } };
  });

  pi.registerCommand(COMMAND_NAME, {
    description: "Show or set OpenAI controls: service-tier, web-search, reload, status",
    getArgumentCompletions: (prefix: string) => getCommandCompletions(prefix),
    handler: async (args, ctx) => {
      const selectedArgs = args.trim() || (await selectCommandArgs(ctx));
      if (!selectedArgs) {
        ctx.ui.notify("OpenAI controls unchanged", "info");
        return;
      }

      const command = parseCommand(selectedArgs);
      if (!command) {
        ctx.ui.notify(`Usage: /${COMMAND_NAME} status | reload | service-tier <auto|default|flex|priority> | web-search <live|cached|disabled>`, "error");
        return;
      }

      if (command.action === "status") {
        ctx.ui.notify(formatStatusMessage(state, config, ctx), "info");
        return;
      }

      if (command.action === "reload") {
        config = loadOpenAIControlsConfig(ctx.cwd, ctx.isProjectTrusted());
        resetStateFromConfig(state, config);
        syncActiveWebSearchTool(pi, ctx, state, config);
        ctx.ui.notify(`OpenAI controls reloaded from settings.json: service-tier=${state.serviceTier}, web-search=${state.webSearchMode}`, "info");
        return;
      }

      if (command.action === "service-tier") {
        const selectedServiceTier = parseServiceTier(command.value) ?? (await selectServiceTier(ctx));
        if (!selectedServiceTier) {
          ctx.ui.notify(`OpenAI service tier unchanged: ${state.serviceTier}`, "info");
          return;
        }

        state.serviceTier = selectedServiceTier;
        const settingsPath = saveOpenAIControlsStateToSettings(
          ctx.cwd,
          ctx.isProjectTrusted(),
          state,
        );
        config = loadOpenAIControlsConfig(ctx.cwd, ctx.isProjectTrusted());
        syncActiveWebSearchTool(pi, ctx, state, config);
        const providerServiceTier = getSupportedProviderServiceTier(state.serviceTier, ctx.model) ?? "omitted";
        ctx.ui.notify(`OpenAI service tier: ${state.serviceTier} (applied: ${providerServiceTier}; saved: ${settingsPath})`, "info");
        return;
      }

      if (command.action === "web-search") {
        const selectedMode = parseWebSearchCommandMode(command.value) || (await selectWebSearchMode(ctx));
        if (!selectedMode) {
          ctx.ui.notify(`OpenAI native web search unchanged: ${state.webSearchMode}`, "info");
          return;
        }

        state.webSearchMode = selectedMode;
        const settingsPath = saveOpenAIControlsStateToSettings(
          ctx.cwd,
          ctx.isProjectTrusted(),
          state,
        );
        config = loadOpenAIControlsConfig(ctx.cwd, ctx.isProjectTrusted());
        syncActiveWebSearchTool(pi, ctx, state, config);
        ctx.ui.notify(`OpenAI native web search: ${state.webSearchMode} (saved: ${settingsPath})`, "info");
      }
    },
  });
}

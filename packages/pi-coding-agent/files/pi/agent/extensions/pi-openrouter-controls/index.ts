import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const COMMAND_NAME = "openrouter-controls";
const CONFIG_FILE_NAME = "pi-openrouter-controls.json";
const MAX_OPENROUTER_SESSION_ID_LENGTH = 256;
const VALID_OPENROUTER_QUANTIZATIONS = new Set(["int4", "int8", "fp4", "fp6", "fp8", "fp16", "bf16", "fp32"]);

type JsonRecord = Record<string, unknown>;

type OpenRouterControlsConfig = {
  openrouter: {
    quantizations?: string[];
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

function parseQuantizations(value: unknown, context: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw new Error(`${context} must be an array of strings`);

  return value.map((item, index) => {
    if (typeof item !== "string") throw new Error(`${context}[${index}] must be a string`);

    const quantization = item.trim().toLowerCase();
    if (!quantization) throw new Error(`${context}[${index}] must be a non-empty string`);
    if (!VALID_OPENROUTER_QUANTIZATIONS.has(quantization)) {
      throw new Error(
        `${context}[${index}] must be one of: ${Array.from(VALID_OPENROUTER_QUANTIZATIONS).join(", ")}`,
      );
    }
    return quantization;
  });
}

function parseRawConfig(raw: JsonRecord, path: string): Partial<OpenRouterControlsConfig> {
  const openrouter = isRecord(raw.openrouter) ? raw.openrouter : undefined;
  if (!openrouter) return {};

  const quantizations = parseQuantizations(openrouter.quantizations, `${path}.openrouter.quantizations`);

  return {
    openrouter: {
      ...(quantizations !== undefined ? { quantizations } : {}),
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
      ...(config.openrouter?.quantizations !== undefined ? { quantizations: config.openrouter.quantizations } : {}),
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

function areStringArraysEqual(left: unknown, right: unknown): boolean {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false;
  }
  return left.every((value, index) => value === right[index]);
}

function getSessionId(ctx: ExtensionContext): string | undefined {
  const sessionId = ctx.sessionManager.getSessionId().trim();
  if (!sessionId) return undefined;

  // OpenRouter rejects session_id values longer than 256 chars; hash custom pi IDs that exceed it.
  if (sessionId.length > MAX_OPENROUTER_SESSION_ID_LENGTH) {
    return `pi-${createHash("sha256").update(sessionId).digest("hex")}`;
  }

  return sessionId;
}

function rewritePayload(payload: unknown, ctx: ExtensionContext, config: OpenRouterControlsConfig): unknown {
  if (!isOpenRouterModel(ctx.model) || !isRecord(payload)) {
    return undefined;
  }

  let nextPayload: JsonRecord = payload;

  const sessionId = getSessionId(ctx);
  if (sessionId && payload.session_id !== sessionId) {
    nextPayload = { ...nextPayload, session_id: sessionId };
  }

  if (config.openrouter.quantizations && config.openrouter.quantizations.length > 0) {
    const currentProvider = isRecord(nextPayload.provider) ? nextPayload.provider : {};
    const nextProvider = { ...currentProvider, quantizations: config.openrouter.quantizations };
    if (!areStringArraysEqual(currentProvider.quantizations, nextProvider.quantizations)) {
      nextPayload = { ...nextPayload, provider: nextProvider };
    }
  }

  return nextPayload === payload ? undefined : nextPayload;
}

function formatStatus(config: OpenRouterControlsConfig, cwd: string): string {
  const lines = [
    `OpenRouter controls`,
    `Config: ${getConfigPaths(cwd).join(", ")}`,
    `quantizations: ${config.openrouter.quantizations?.join(", ") || "(none)"}`,
  ];
  return lines.join("\n");
}

export default function openRouterControls(pi: ExtensionAPI) {
  let config = loadConfig();

  pi.on("session_start", async (_event, ctx) => {
    config = loadConfig(ctx.cwd);
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
        ctx.ui.notify("OpenRouter controls reloaded", "info");
        return;
      }

      ctx.ui.notify(`Usage: /${COMMAND_NAME} status | reload`, "error");
    },
  });
}

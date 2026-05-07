import type { CurrentModel } from "./types";

export function isOpenAICodexModel(model: CurrentModel): boolean {
  return (model?.provider ?? "").toLowerCase() === "openai-codex";
}

export function isOpenAIProviderModel(model: CurrentModel): boolean {
  const provider = (model?.provider ?? "").toLowerCase();
  return provider === "openai" || provider === "openai-codex" || provider === "azure-openai-responses";
}

export function isOpenAIResponsesPayloadModel(model: CurrentModel): boolean {
  if (!isOpenAIProviderModel(model)) return false;
  const api = (model?.api ?? "").toLowerCase();
  return api === "openai-responses" || api === "azure-openai-responses" || api === "openai-codex-responses";
}

export function supportsTextAndImageSearch(model: CurrentModel): boolean {
  // Mirrors pi-codex-conversion: Spark lacks multimodal OpenAI native web search.
  return isOpenAICodexModel(model) && !(model?.id ?? "").toLowerCase().includes("spark");
}

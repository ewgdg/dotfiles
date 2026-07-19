import { describe, expect, test } from "bun:test";
import {
  rewriteInternalCitationTags,
  rewriteOpenAINativeWebSearchTools,
  rewriteWebSearchCitationInstructions,
} from "./web-search";
import type { CurrentModel, WebSearchConfig } from "./types";

const codexModel = {
  provider: "openai-codex",
  id: "gpt-5.6-sol",
  api: "openai-codex-responses",
  input: ["text", "image"],
} as CurrentModel;

const anthropicModel = {
  provider: "anthropic",
  id: "claude",
  api: "anthropic-messages",
  input: ["text"],
} as CurrentModel;

const config: WebSearchConfig = { mode: "live" };

describe("rewriteInternalCitationTags", () => {
  test("renders one opaque citation as parenthetical metadata", () => {
    expect(rewriteInternalCitationTags("Claim. citeturn1search0")).toBe("Claim. (web source)");
  });

  test("includes the source count for grouped opaque citations", () => {
    expect(rewriteInternalCitationTags("Claim. citeturn1search0turn1search1")).toBe(
      "Claim. (2 web sources)",
    );
  });
});

describe("rewriteWebSearchCitationInstructions", () => {
  test("appends citation guidance when Codex web search is enabled", () => {
    expect(
      rewriteWebSearchCitationInstructions(
        { instructions: "Existing guidance." },
        "live",
        codexModel,
      ),
    ).toEqual({
      instructions:
        "Existing guidance.\n\n<guidance>\nWhen citing web search sources, use Markdown links with the source URL instead of internal citation tags.\n</guidance>",
    });
  });

  test("does not add citation guidance when web search is disabled", () => {
    expect(rewriteWebSearchCitationInstructions({}, "disabled", codexModel)).toBeUndefined();
  });

  test("does not duplicate existing citation guidance", () => {
    const instructions =
      "<guidance>\nWhen citing web search sources, use Markdown links with the source URL instead of internal citation tags.\n</guidance>";
    expect(rewriteWebSearchCitationInstructions({ instructions }, "live", codexModel)).toBeUndefined();
  });
});

describe("rewriteOpenAINativeWebSearchTools", () => {
  test("appends native web search without requiring a synthetic function tool", () => {
    const payload = {
      tools: [{ type: "function", name: "read", parameters: {} }],
    };

    expect(rewriteOpenAINativeWebSearchTools(payload, "live", codexModel, config)).toEqual({
      tools: [
        { type: "function", name: "read", parameters: {} },
        {
          type: "web_search",
          external_web_access: true,
          search_content_types: ["text", "image"],
        },
      ],
    });
  });

  test("creates the tool list when the provider payload has none", () => {
    expect(rewriteOpenAINativeWebSearchTools({}, "cached", codexModel, config)).toEqual({
      tools: [
        {
          type: "web_search",
          external_web_access: false,
          search_content_types: ["text", "image"],
        },
      ],
    });
  });

  test("replaces native web-search entries with one deterministic final entry", () => {
    const payload = {
      tools: [
        { type: "web_search", external_web_access: false },
        { type: "function", name: "bash", parameters: {} },
      ],
    };

    expect(rewriteOpenAINativeWebSearchTools(payload, "live", codexModel, config)).toEqual({
      tools: [
        { type: "function", name: "bash", parameters: {} },
        {
          type: "web_search",
          external_web_access: true,
          search_content_types: ["text", "image"],
        },
      ],
    });
  });

  test("removes web-search entries when disabled", () => {
    const payload = {
      tools: [
        { type: "function", name: "read", parameters: {} },
        { type: "web_search", external_web_access: true },
      ],
    };

    expect(rewriteOpenAINativeWebSearchTools(payload, "disabled", codexModel, config)).toEqual({
      tools: [{ type: "function", name: "read", parameters: {} }],
    });
  });

  test("does not alter non-Codex payloads", () => {
    expect(rewriteOpenAINativeWebSearchTools({ tools: [] }, "live", anthropicModel, config)).toBeUndefined();
  });
});

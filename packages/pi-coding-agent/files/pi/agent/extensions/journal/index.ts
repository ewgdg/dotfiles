import { join } from "node:path";
import { homedir } from "node:os";
import { defineTool, type ExtensionAPI } from "@mariozechner/pi-coding-agent";
import type { Model } from "@mariozechner/pi-ai";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "typebox";

interface JournalWriteDetails {
	path: string;
	author: string;
	highlight: string;
}

const JOURNAL_TOOL_NAME = "journal_write";
const SCRIPT_PATH = process.env.JOURNAL_WRITE_SCRIPT ?? join(homedir(), ".agents", "skills", "journal", "run.sh");
const EXECUTION_TIMEOUT_MS = 30_000;

function slugPart(value: string): string {
	return value
		.toLowerCase()
		.replace(/[^a-z0-9._+-]+/g, "-")
		.replace(/^-+|-+$/g, "");
}

function authorFor(model: Model<any> | undefined): string {
	if (!model) return "agent-pi";

	const provider = slugPart(model.provider);
	const modelId = slugPart(model.id);
	const suffix = [provider, modelId].filter(Boolean).join("-");

	return suffix ? `agent-pi-${suffix}` : "agent-pi";
}

function journalMarker(highlight: string | undefined): string {
	return highlight ? `[journal logged: ${highlight}]` : "[journal logged]";
}

function collectJournalHighlights(messages: any[]): Map<string, string> {
	const highlights = new Map<string, string>();

	for (const message of messages) {
		if (message?.role !== "toolResult" || message.toolName !== JOURNAL_TOOL_NAME) continue;
		const highlight = typeof message.details?.highlight === "string" ? message.details.highlight : undefined;
		if (highlight && typeof message.toolCallId === "string") highlights.set(message.toolCallId, highlight);
	}

	return highlights;
}

function compactJournalContext(messages: any[]): any[] {
	const journalHighlights = collectJournalHighlights(messages);
	const compactedMessages: any[] = [];

	for (const message of messages) {
		if (message?.role === "toolResult" && message.toolName === JOURNAL_TOOL_NAME) continue;

		if (message?.role !== "assistant" || !Array.isArray(message.content)) {
			compactedMessages.push(message);
			continue;
		}

		const content = message.content.flatMap((block: any) => {
			if (block?.type !== "toolCall" || block.name !== JOURNAL_TOOL_NAME) return [block];

			const highlight =
				typeof block.arguments?.highlight === "string"
					? block.arguments.highlight
					: typeof block.id === "string"
						? journalHighlights.get(block.id)
						: undefined;

			return [{ type: "text", text: journalMarker(highlight) }];
		});

		compactedMessages.push({ ...message, content });
	}

	return compactedMessages;
}

export default function (pi: ExtensionAPI) {
	let currentModel: Model<any> | undefined;

	pi.on("model_select", async (event) => {
		currentModel = event.model;
	});

	pi.on("context", async (event) => {
		return { messages: compactJournalContext(event.messages) };
	});

	pi.registerTool(
		defineTool({
			name: JOURNAL_TOOL_NAME,
			label: "Journal Write",
			description:
				"Create an Obsidian journal entry with Highlight and Journal fields, set author automatically.",
			promptSnippet: "Log meaningful future-review deltas to Obsidian",
			promptGuidelines: [
				"journal_write is agent-triggered: decide after meaningful work. If criteria pass, write one journal entry automatically after completing the work worth journaling; do not wait for the user to ask. Criteria: meaningful progress, a reusable lesson or insight, a corrected assumption, a consequential decision, a workflow improvement, a resolved blocker, a useful idea or reframe, or a surprise that changes understanding or direction.",
				"Do not use journal_write for trivial activity, routine updates, implementation noise, obvious facts, or low-signal thoughts.",
				"Do not journal merely because journaling machinery was used; log skill/workflow changes only when the change itself has future review value.",
				"journal_write Highlight must be a short concrete proposition: say what changed, not a vague topic like Update or Progress.",
				"journal_write Journal must use $caveman style compacted language and be concise, information-dense: capture the event, what changed, and why it may matter. No padding. Prefer 1-4 tight sentences or compact bullets.",
			],
			parameters: Type.Object({
				highlight: Type.String({ description: "Short concrete proposition for the journal entry" }),
				journal: Type.String({
					description: "Information-dense reflection capturing the event, what changed, and why it may matter",
				}),
			}),

			async execute(_toolCallId, params, signal) {
				const author = authorFor(currentModel);
				const result = await pi.exec(SCRIPT_PATH, [params.highlight, params.journal, author], {
					signal,
					timeout: EXECUTION_TIMEOUT_MS,
				});

				if (result.code !== 0) {
					const stderr = result.stderr.trim();
					const stdout = result.stdout.trim();
					throw new Error(stderr || stdout || `journal_write failed with exit code ${result.code}`);
				}

				const path = result.stdout.trim().split(/\r?\n/).at(-1) ?? "";
				if (!path) throw new Error("journal_write did not return a journal path");

				return {
					content: [{ type: "text", text: `logged: ${path}` }],
					details: { path, author, highlight: params.highlight } satisfies JournalWriteDetails,
					terminate: true,
				};
			},

			renderResult(result, _options, theme) {
				const details = result.details as JournalWriteDetails | undefined;
				const text = details ? `journal: ${details.path}` : "journal logged";
				return new Text(theme.fg("muted", text), 0, 0);
			},
		}),
	);
}

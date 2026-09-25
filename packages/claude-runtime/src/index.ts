/**
 * The one place in this codebase that talks to Claude.
 *
 * Per docs/architecture.md: everything else (tools, the desktop UI,
 * eventually the companion) goes through this adapter rather than
 * calling Anthropic directly, so the auth path and model choice stay in
 * one configurable spot.
 *
 * Auth path note (master prompt section 2): the official Agent SDK is
 * the preferred embedded integration long-term, since it gives us
 * built-in tool use, sessions and permission hooks for free. This first
 * working slice uses the plain Anthropic TypeScript SDK against an API
 * key (the documented, verifiable route available right now) so
 * Milestone 1 has a real, testable end-to-end chat loop. Swapping the
 * inside of `ClaudeRuntime.streamChat` for the Agent SDK later doesn't
 * change this module's exported shape. Do not assume a Claude.ai
 * subscription covers this API usage - it needs its own API key, and
 * the setup UI must say so honestly (see SetupStatus).
 */

import Anthropic from "@anthropic-ai/sdk";
import type {
  ChatMessage,
  ChatStreamDelta,
  ClaudeConnectionState,
  SetupStatus,
} from "@jarvis/contracts";

export class ClaudeNotConfiguredError extends Error {
  constructor() {
    super(
      "Claude is not connected: no API key configured. Set ANTHROPIC_API_KEY " +
        "or complete setup in the app before sending a chat request."
    );
    this.name = "ClaudeNotConfiguredError";
  }
}

export interface ClaudeRuntimeOptions {
  apiKey: string | undefined;
  model?: string;
}

const DEFAULT_MODEL = "claude-opus-5-5";

export class ClaudeRuntime {
  private readonly client: Anthropic | undefined;
  private readonly model: string;
  private lastError: string | undefined;

  constructor(opts: ClaudeRuntimeOptions) {
    this.model = opts.model ?? DEFAULT_MODEL;
    this.client = opts.apiKey ? new Anthropic({ apiKey: opts.apiKey }) : undefined;
  }

  static fromEnv(): ClaudeRuntime {
    return new ClaudeRuntime({
      apiKey: process.env.ANTHROPIC_API_KEY,
      model: process.env.JARVIS_CLAUDE_MODEL,
    });
  }

  /** Truthful connection state for the setup UI. Never claim "connected" without a key. */
  getSetupStatus(): SetupStatus {
    let state: ClaudeConnectionState = "not-configured";
    let detail: string | undefined;
    if (this.client) {
      state = this.lastError ? "error" : "connected";
      detail = this.lastError;
    } else {
      detail = "No ANTHROPIC_API_KEY configured. Add one in Settings to connect Claude.";
    }
    return { claude: { state, detail } };
  }

  /**
   * Streams a reply to `history` (last message must be role "user").
   * Yields text deltas as they arrive; resolves to the finished message.
   * Pass `signal` to support a real stop button - aborting cancels the
   * underlying HTTP request, it doesn't just stop rendering locally.
   */
  async *streamChat(
    history: ChatMessage[],
    opts: { jobId: string; signal?: AbortSignal }
  ): AsyncGenerator<ChatStreamDelta, ChatMessage> {
    if (!this.client) {
      throw new ClaudeNotConfiguredError();
    }

    const stream = await this.client.messages.create(
      {
        model: this.model,
        max_tokens: 4096,
        messages: history.map((m) => ({ role: m.role, content: m.text })),
        stream: true,
      },
      { signal: opts.signal }
    );

    let full = "";
    try {
      for await (const event of stream) {
        if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
          full += event.delta.text;
          yield { jobId: opts.jobId, textDelta: event.delta.text };
        }
      }
      this.lastError = undefined;
    } catch (err) {
      this.lastError = err instanceof Error ? err.message : String(err);
      throw err;
    }

    return {
      id: opts.jobId,
      role: "assistant",
      text: full,
      createdAt: new Date().toISOString(),
    };
  }
}

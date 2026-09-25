/**
 * The one place in this codebase that talks to Claude.
 *
 * Per docs/architecture.md: everything else (tools, the desktop UI,
 * eventually the companion) goes through this adapter rather than
 * calling Anthropic directly, so the auth path and model choice stay in
 * one configurable spot.
 *
 * Auth path (updated per Marky's explicit ask: he already has Claude
 * Code installed and logged in, and does not want a second, separately
 * billed API key just for Jarvis). Two backends, tried in this order:
 *
 * 1. **cli** - shells out to the `claude` CLI already on his machine,
 *    reusing whatever login Claude Code itself is using. This is the
 *    default whenever the `claude` binary is found on PATH. It's exactly
 *    the "documented CLI programmatic interface" the master prompt
 *    flags as the fallback when the Agent SDK's own auth doesn't fit -
 *    it fits better here, since it's the one path that needs no
 *    separate credential at all.
 * 2. **api** - the plain Anthropic TS SDK against ANTHROPIC_API_KEY, for
 *    anyone who *wants* a separate key (a shared/companion machine
 *    without Claude Code installed, for instance) or as a fallback if
 *    the CLI isn't present.
 *
 * Swapping either backend for the real Agent SDK later doesn't change
 * this module's exported shape.
 */

import crossSpawn from "cross-spawn";
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
      "Claude is not connected: no `claude` CLI found on PATH and no ANTHROPIC_API_KEY " +
        "configured. Install/log in to Claude Code, or add an API key in Settings."
    );
    this.name = "ClaudeNotConfiguredError";
  }
}

export type ClaudeRuntimeMode = "cli" | "api";

export interface ClaudeRuntimeOptions {
  apiKey: string | undefined;
  model?: string;
  /** Force a backend instead of auto-detecting. Mainly for tests. */
  mode?: ClaudeRuntimeMode;
  /** Override the `claude` executable name/path. Mainly for tests. */
  cliBin?: string;
}

const DEFAULT_MODEL = "claude-opus-5-5";

/**
 * True if `<cliBin> --version` runs successfully. Cheap, synchronous, no
 * network call. Uses cross-spawn, not node:child_process directly: on
 * Windows, npm installs `claude` as a `.cmd` shim, and Node's own
 * spawnSync can't launch that without `shell: true` - which Node's docs
 * warn does not safely escape arguments. cross-spawn resolves and
 * invokes the shim correctly without going through a shell, so the
 * prompt text in streamViaCli below can't break out into a command
 * injection. Confirmed by hand: plain spawnSync("claude", ...) throws
 * ENOENT on Windows; this is the actual fix, not a guess.
 */
function detectCli(cliBin: string): boolean {
  try {
    const result = crossSpawn.sync(cliBin, ["--version"], { timeout: 5_000 });
    return result.status === 0;
  } catch {
    return false;
  }
}

export class ClaudeRuntime {
  private readonly mode: ClaudeRuntimeMode | "not-configured";
  private readonly apiClient: Anthropic | undefined;
  private readonly model: string;
  private readonly cliBin: string;
  private lastError: string | undefined;

  constructor(opts: ClaudeRuntimeOptions) {
    this.model = opts.model ?? DEFAULT_MODEL;
    this.cliBin = opts.cliBin ?? "claude";

    if (opts.mode) {
      this.mode = opts.mode;
    } else if (detectCli(this.cliBin)) {
      this.mode = "cli";
    } else if (opts.apiKey) {
      this.mode = "api";
    } else {
      this.mode = "not-configured";
    }

    this.apiClient = opts.apiKey ? new Anthropic({ apiKey: opts.apiKey }) : undefined;
  }

  static fromEnv(): ClaudeRuntime {
    return new ClaudeRuntime({
      apiKey: process.env.ANTHROPIC_API_KEY,
      model: process.env.JARVIS_CLAUDE_MODEL,
      mode: process.env.JARVIS_CLAUDE_MODE as ClaudeRuntimeMode | undefined,
      cliBin: process.env.JARVIS_CLAUDE_CLI_BIN,
    });
  }

  /**
   * Truthful connection state for the setup UI. "cli" only confirms the
   * binary runs, not that it's actually logged in - a real login failure
   * still surfaces honestly as a streamed error on the first chat, per
   * streamChat's error handling below, never a fabricated reply.
   */
  getSetupStatus(): SetupStatus {
    let state: ClaudeConnectionState = "not-configured";
    let detail: string | undefined;
    if (this.mode === "cli") {
      state = this.lastError ? "error" : "connected";
      detail = this.lastError ?? "Using the `claude` CLI already logged in on this machine.";
    } else if (this.mode === "api" && this.apiClient) {
      state = this.lastError ? "error" : "connected";
      detail = this.lastError;
    } else {
      detail =
        "No `claude` CLI found on PATH and no ANTHROPIC_API_KEY configured. " +
        "Install Claude Code and log in, or add an API key in Settings.";
    }
    return { claude: { state, detail } };
  }

  /**
   * Streams a reply to `history` (last message must be role "user").
   * Yields text deltas as they arrive; resolves to the finished message.
   * Pass `signal` to support a real stop button - aborting cancels the
   * underlying request/process, it doesn't just stop rendering locally.
   */
  async *streamChat(
    history: ChatMessage[],
    opts: { jobId: string; signal?: AbortSignal }
  ): AsyncGenerator<ChatStreamDelta, ChatMessage> {
    if (this.mode === "cli") return yield* this.streamViaCli(history, opts);
    if (this.mode === "api" && this.apiClient) return yield* this.streamViaApi(history, opts);
    throw new ClaudeNotConfiguredError();
  }

  private async *streamViaApi(
    history: ChatMessage[],
    opts: { jobId: string; signal?: AbortSignal }
  ): AsyncGenerator<ChatStreamDelta, ChatMessage> {
    const stream = await this.apiClient!.messages.create(
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

    return { id: opts.jobId, role: "assistant", text: full, createdAt: new Date().toISOString() };
  }

  /**
   * Runs `claude -p <prompt> --output-format stream-json --verbose`,
   * parsing its newline-delimited JSON on stdout. Each `stream_event`
   * line wraps the same Anthropic message-stream shape the API path
   * above already handles (content_block_delta / text_delta), so the
   * per-chunk parsing is identical; only getting there differs.
   *
   * Stateless per call, like the API path: the whole `history` is
   * flattened into one prompt rather than relying on the CLI's own
   * --resume/--continue session state, so this stays consistent with
   * services/core owning conversation history in its own job store.
   * --permission-prompts none: this runs unattended with no terminal to
   * answer a prompt, so anything that would need approval is refused
   * outright rather than hanging.
   */
  private async *streamViaCli(
    history: ChatMessage[],
    opts: { jobId: string; signal?: AbortSignal }
  ): AsyncGenerator<ChatStreamDelta, ChatMessage> {
    const prompt = flattenHistory(history);
    const child = crossSpawn(
      this.cliBin,
      [
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--permission-prompts",
        "none",
        "--model",
        this.model,
      ],
      { signal: opts.signal, stdio: ["ignore", "pipe", "pipe"] }
    );

    let full = "";
    let resultText: string | undefined;
    let resultError: string | undefined;
    let buffer = "";
    let stderr = "";
    child.stderr?.on("data", (chunk: Buffer) => (stderr += chunk.toString()));

    const lines = (async function* () {
      for await (const chunk of child.stdout!) {
        buffer += (chunk as Buffer).toString();
        const parts = buffer.split("\n");
        buffer = parts.pop() ?? "";
        yield* parts;
      }
      if (buffer) yield buffer;
    })();

    try {
      for await (const line of lines) {
        if (!line.trim()) continue;
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(line);
        } catch {
          continue; // a non-JSON stray line shouldn't kill the whole stream
        }

        if (msg.type === "stream_event") {
          const event = msg.event as { type?: string; delta?: { type?: string; text?: string } };
          if (event?.type === "content_block_delta" && event.delta?.type === "text_delta") {
            const text = event.delta.text ?? "";
            full += text;
            yield { jobId: opts.jobId, textDelta: text };
          }
        } else if (msg.type === "result") {
          if (msg.is_error) resultError = String(msg.result ?? "claude CLI reported an error");
          else resultText = String(msg.result ?? full);
        }
      }

      await new Promise<void>((resolve, reject) => {
        child.on("exit", (code) => {
          if (opts.signal?.aborted) return resolve(); // cancelled - not a real failure
          if (code === 0) resolve();
          else reject(new Error(`claude CLI exited with code ${code}: ${stderr.trim() || "no stderr"}`));
        });
        child.on("error", reject);
      });

      if (resultError) throw new Error(resultError);
      this.lastError = undefined;
    } catch (err) {
      this.lastError = err instanceof Error ? err.message : String(err);
      throw err;
    }

    return {
      id: opts.jobId,
      role: "assistant",
      text: resultText ?? full,
      createdAt: new Date().toISOString(),
    };
  }
}

/** The CLI's `-p` mode takes one prompt string, not a message array - flatten history into it. */
function flattenHistory(history: ChatMessage[]): string {
  if (history.length === 1) return history[0].text;
  return history.map((m) => `${m.role === "user" ? "Human" : "Assistant"}: ${m.text}`).join("\n\n");
}

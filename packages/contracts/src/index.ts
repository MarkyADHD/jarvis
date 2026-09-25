/**
 * Shared types for Jarvis: the wire format every process (services/core,
 * apps/desktop, apps/companion, packages/claude-runtime) agrees on.
 *
 * See docs/architecture.md for the reasoning. Nothing here talks to a
 * database or a network - it's just shapes.
 */

// ---------------------------------------------------------------------------
// Jobs (master prompt section 5: "represent each job with an ID, initiating
// identity/device, user goal, ... state, steps, timestamps, cost,
// cancellation token, result evidence and output artifacts")
// ---------------------------------------------------------------------------

export type JobState =
  | "queued"
  | "running"
  | "waiting-for-input"
  | "waiting-for-approval"
  | "paused"
  | "cancelling"
  | "cancelled"
  | "succeeded"
  | "failed"
  | "outcome-unknown";

export type InputOrigin =
  | "owner-voice"
  | "owner-desktop"
  | "paired-phone"
  | "scheduled-routine"
  | "external-event"
  | "web-page"
  | "document"
  | "chat-message";

export interface JobStep {
  id: string;
  description: string;
  startedAt?: string; // ISO 8601
  finishedAt?: string;
  evidence?: string;
}

export interface Job {
  id: string;
  goal: string;
  origin: InputOrigin;
  state: JobState;
  createdAt: string;
  updatedAt: string;
  steps: JobStep[];
  /** Known/estimated monetary or token cost so far. Never fabricated. */
  cost?: { estimatedUsd?: number; inputTokens?: number; outputTokens?: number };
  /** Set once the job reaches a terminal state. Never claim success without this. */
  result?: {
    outcome: "succeeded" | "failed" | "unknown";
    summary: string;
    artifacts?: string[]; // file paths, URLs, or other evidence
  };
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  createdAt: string;
}

/** One incremental piece of a streamed assistant reply. */
export interface ChatStreamDelta {
  jobId: string;
  textDelta: string;
}

export interface ChatStreamDone {
  jobId: string;
  message: ChatMessage;
}

export interface ChatStreamError {
  jobId: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Setup / connection status - must always be truthful (master prompt
// section 3: "Production screens must show truthful connection states.")
// ---------------------------------------------------------------------------

export type ClaudeConnectionState =
  | "not-configured"
  | "connecting"
  | "connected"
  | "error";

export interface SetupStatus {
  claude: {
    state: ClaudeConnectionState;
    detail?: string;
  };
}

// ---------------------------------------------------------------------------
// Tool contracts (master prompt section 5)
// ---------------------------------------------------------------------------

export type ToolPermissionCategory =
  | "read-only"
  | "routine-local-action"
  | "requires-approval"
  | "blocked";

export interface ToolContract<Input = unknown, Output = unknown> {
  name: string;
  version: string;
  description: string;
  permissionCategory: ToolPermissionCategory;
  supportsDryRun: boolean;
  supportsCancellation: boolean;
  /** Not enforced by the type system here - each tool validates its own I/O. */
  __inputType?: Input;
  __outputType?: Output;
}

// ---------------------------------------------------------------------------
// Voice (master prompt section 6). Shared between services/core and
// services/voice (Python) via the JSON messages sent over their local
// connection - this is the agreed shape, not a claim that the voice
// service exists yet. See docs/build-ledger.md for what's actually built.
// ---------------------------------------------------------------------------

export type VoiceState =
  | "dormant"
  | "listening"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "error";

export interface VoiceStateEvent {
  state: VoiceState;
  reason?: string;
  at: string; // ISO 8601
}

/** "Jarvis stop" / hotkey / "sleep" - always distinct from a normal turn ending. */
export type VoiceControlCommand = "stop" | "sleep" | "wake";


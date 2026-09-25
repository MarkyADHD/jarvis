/**
 * The only bridge between the sandboxed renderer and the main process.
 * Deliberately narrow - the renderer can send a chat, cancel a chat and
 * ask for setup status, and nothing else (docs/architecture.md: "no
 * arbitrary executeShell bridge to renderer content").
 */

import { contextBridge, ipcRenderer } from "electron";

// This file compiles to CommonJS (.cjs) - Electron's sandboxed preload
// loader requires that regardless of the rest of the app being ESM (see
// docs/build-ledger.md for the bug this fixes). @jarvis/contracts is an
// ESM package, and TypeScript's Node16/NodeNext module resolution
// refuses to let a CJS file reference an ESM package's types at all
// (TS1479), even for a type-only, zero-runtime-emit reference - so
// these mirror the handful of contracts/src/index.ts shapes this file
// actually needs rather than importing them. Keep in sync if those
// shapes change; nothing else in this small bridge needs the real
// import machinery.
interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: string;
}
interface ChatStreamDelta {
  jobId: string;
  textDelta: string;
}
interface ChatStreamDone {
  jobId: string;
  message: ChatMessage;
}
interface ChatStreamError {
  jobId: string;
  message: string;
}
interface SetupStatus {
  claude: { state: "not-configured" | "connecting" | "connected" | "error"; detail?: string };
}

const api = {
  getSetupStatus: (): Promise<SetupStatus> => ipcRenderer.invoke("setup:get"),
  sendChat: (history: ChatMessage[]): Promise<{ jobId: string }> => ipcRenderer.invoke("chat:send", history),
  cancelChat: (jobId: string): Promise<{ cancelled: boolean }> => ipcRenderer.invoke("chat:cancel", jobId),
  onChatDelta: (cb: (d: ChatStreamDelta) => void) =>
    ipcRenderer.on("chat:delta", (_e, data: ChatStreamDelta) => cb(data)),
  onChatDone: (cb: (d: ChatStreamDone) => void) => ipcRenderer.on("chat:done", (_e, data: ChatStreamDone) => cb(data)),
  onChatError: (cb: (d: ChatStreamError) => void) =>
    ipcRenderer.on("chat:error", (_e, data: ChatStreamError) => cb(data)),
  onChatCancelled: (cb: (d: ChatStreamError) => void) =>
    ipcRenderer.on("chat:cancelled", (_e, data: ChatStreamError) => cb(data)),
};

contextBridge.exposeInMainWorld("jarvis", api);

export type JarvisBridge = typeof api;

/**
 * The only bridge between the sandboxed renderer and the main process.
 * Deliberately narrow - the renderer can send a chat, cancel a chat and
 * ask for setup status, and nothing else (docs/architecture.md: "no
 * arbitrary executeShell bridge to renderer content").
 */

import { contextBridge, ipcRenderer } from "electron";
import type { ChatMessage, ChatStreamDelta, ChatStreamDone, ChatStreamError, SetupStatus } from "@jarvis/contracts";

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

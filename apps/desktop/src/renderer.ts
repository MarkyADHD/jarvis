/**
 * Renderer UI: a truthful setup banner plus a minimal chat loop with a
 * working stop button. Plain DOM, no framework yet - this proves the
 * main/preload/core wiring end to end before layering React on top per
 * docs/architecture.md. Runs sandboxed (contextIsolation, no Node
 * integration); everything it can do goes through `window.jarvis`
 * (see preload.ts).
 */

// preload.ts compiles to preload.cjs (Electron's sandboxed preload
// loader requires CommonJS) - reference that output extension so the
// type import resolves to its declaration file (preload.d.cts).
import type { JarvisBridge } from "./preload.cjs";

declare global {
  interface Window {
    jarvis: JarvisBridge;
  }
}

interface UiMessage {
  role: "user" | "assistant";
  text: string;
}

const messages: UiMessage[] = [];
let currentJobId: string | undefined;

const setupBanner = document.getElementById("setup-banner")!;
const messageList = document.getElementById("messages")!;
const input = document.getElementById("input") as HTMLTextAreaElement;
const sendButton = document.getElementById("send") as HTMLButtonElement;
const stopButton = document.getElementById("stop") as HTMLButtonElement;

function render(): void {
  messageList.innerHTML = "";
  for (const m of messages) {
    const el = document.createElement("div");
    el.className = `message message-${m.role}`;
    el.textContent = m.text;
    messageList.appendChild(el);
  }
  messageList.scrollTop = messageList.scrollHeight;
}

async function refreshSetupStatus(): Promise<void> {
  const status = await window.jarvis.getSetupStatus();
  if (status.claude.state === "connected") {
    setupBanner.textContent = "";
    setupBanner.hidden = true;
    sendButton.disabled = false;
  } else {
    setupBanner.textContent =
      status.claude.detail ?? "Claude is not connected. Add an API key in Settings to chat.";
    setupBanner.hidden = false;
    sendButton.disabled = true;
  }
}

async function send(): Promise<void> {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  messages.push({ role: "user", text });
  messages.push({ role: "assistant", text: "" });
  render();

  sendButton.disabled = true;
  stopButton.disabled = false;

  const history = messages
    .slice(0, -1)
    .map((m) => ({ id: crypto.randomUUID(), role: m.role, text: m.text, createdAt: new Date().toISOString() }));

  const { jobId } = await window.jarvis.sendChat(history);
  currentJobId = jobId;
}

window.jarvis.onChatDelta((delta) => {
  if (delta.jobId !== currentJobId) return;
  const last = messages[messages.length - 1];
  last.text += delta.textDelta;
  render();
});

function finishTurn(): void {
  currentJobId = undefined;
  sendButton.disabled = false;
  stopButton.disabled = true;
}

window.jarvis.onChatDone(() => finishTurn());
window.jarvis.onChatError((err) => {
  const last = messages[messages.length - 1];
  last.text = `[error] ${err.message}`;
  render();
  finishTurn();
});
window.jarvis.onChatCancelled(() => {
  const last = messages[messages.length - 1];
  last.text += " [stopped]";
  render();
  finishTurn();
});

sendButton.addEventListener("click", () => void send());
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    void send();
  }
});
stopButton.addEventListener("click", () => {
  if (currentJobId) void window.jarvis.cancelChat(currentJobId);
});

stopButton.disabled = true;
void refreshSetupStatus();
render();

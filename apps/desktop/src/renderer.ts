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
const talkButton = document.getElementById("talk") as HTMLButtonElement;

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

async function sendText(text: string): Promise<void> {
  if (!text) return;
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

async function send(): Promise<void> {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  await sendText(text);
}

// Speaks the assistant's finished reply out loud once a turn completes.
// Voice may not be set up yet (no Piper voice model downloaded - see
// docs/build-ledger.md), so a failure here is swallowed rather than
// shown as a chat error: text chat must keep working either way.
function speakReply(text: string): void {
  if (!text.trim()) return;
  void window.jarvis.voiceSpeak(text).catch((err) => {
    console.warn("voice speak unavailable:", err);
  });
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

window.jarvis.onChatDone((data) => {
  speakReply(data.message.text);
  finishTurn();
});
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

// Hold-to-talk (Milestone 2): press, speak, release. Mirrors a physical
// push-to-talk button rather than a toggle, per the master prompt - no
// wake-word listening yet. pointerup/pointerleave both stop the capture
// so dragging off the button while held doesn't leave it recording
// forever.
let talking = false;

async function startTalking(): Promise<void> {
  if (talking) return;
  talking = true;
  talkButton.classList.add("recording");
  try {
    await window.jarvis.voicePttStart();
  } catch (err) {
    console.warn("voice unavailable:", err);
    talking = false;
    talkButton.classList.remove("recording");
  }
}

async function stopTalking(): Promise<void> {
  if (!talking) return;
  talking = false;
  talkButton.classList.remove("recording");
  try {
    const { transcript } = await window.jarvis.voicePttStop();
    if (transcript.trim()) await sendText(transcript.trim());
  } catch (err) {
    console.warn("voice unavailable:", err);
  }
}

talkButton.addEventListener("pointerdown", () => void startTalking());
talkButton.addEventListener("pointerup", () => void stopTalking());
talkButton.addEventListener("pointerleave", () => void stopTalking());

stopButton.disabled = true;
void refreshSetupStatus();
render();

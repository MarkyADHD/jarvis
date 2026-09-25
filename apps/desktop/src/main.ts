/**
 * Electron main process. Owns the window, spawns/talks to the
 * @jarvis/core backend, and is the only place holding the core API's
 * auth token - the renderer never sees it directly (hardened per
 * docs/architecture.md: context isolation, no Node integration in the
 * renderer, narrow preload API).
 *
 * NOT RUNTIME-VERIFIED in this session: this cloud container has no
 * display and Electron itself wasn't installed here (a large binary
 * with nothing to render against). Typechecked only. Real verification
 * needs `npm install` + `npm start` on Marky's actual Windows machine.
 * See docs/build-ledger.md.
 */

import { app, BrowserWindow, ipcMain, session } from "electron";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CORE_PORT = Number(process.env.JARVIS_CORE_PORT ?? 8765);
const CORE_BASE = `http://127.0.0.1:${CORE_PORT}`;
const VOICE_PORT = Number(process.env.JARVIS_VOICE_PORT ?? 8788);
const VOICE_BASE = `http://127.0.0.1:${VOICE_PORT}`;

function resolveDataDir(): string {
  if (process.env.JARVIS_DATA_DIR) return process.env.JARVIS_DATA_DIR;
  if (process.platform === "win32" && existsSync("E:\\")) return "E:\\Jarvis\\data";
  return join(__dirname, "..", "..", "..", ".data");
}

let coreProcess: ChildProcess | undefined;
let coreToken = "";
let voiceProcess: ChildProcess | undefined;
let voiceToken = ""; // empty means "not available" - voice IPC handlers degrade to an error instead of throwing

function startCore(): void {
  const corePath = join(__dirname, "..", "..", "..", "services", "core", "dist", "server.js");
  coreProcess = spawn(process.execPath, [corePath], {
    env: process.env,
    stdio: "inherit",
  });
  coreProcess.on("exit", (code) => {
    console.error(`jarvis core exited unexpectedly (code ${code}). Chat will show as disconnected.`);
  });
}

// The voice sidecar is optional at this stage (Milestone 2 in progress -
// see docs/build-ledger.md): if Python or its deps aren't installed yet,
// the app still works for text chat, it just can't hear or speak. Spawn
// failures are logged, not thrown, so a missing voice setup never takes
// the whole desktop app down with it.
function startVoice(): void {
  const voicePath = join(__dirname, "..", "..", "..", "services", "voice", "voice_service.py");
  const pythonBin = process.env.JARVIS_PYTHON_BIN ?? (process.platform === "win32" ? "python" : "python3");
  voiceProcess = spawn(pythonBin, [voicePath], { env: process.env, stdio: "inherit" });
  voiceProcess.on("error", (err) => {
    console.error(`jarvis voice service failed to start (${err.message}). Voice will be unavailable.`);
  });
  voiceProcess.on("exit", (code) => {
    if (code !== 0) console.error(`jarvis voice service exited unexpectedly (code ${code}). Voice will be unavailable.`);
  });
}

async function waitForCoreToken(timeoutMs = 10_000): Promise<string> {
  const tokenPath = join(resolveDataDir(), "core-token");
  const start = Date.now();
  let token: string | undefined;
  while (Date.now() - start < timeoutMs) {
    if (existsSync(tokenPath)) {
      token = readFileSync(tokenPath, "utf8").trim();
      break;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  if (!token) throw new Error(`core-token never appeared at ${tokenPath} - is the core service running?`);

  // The token file persists across restarts (same file every launch), so
  // its existence alone doesn't mean *this* process's server is actually
  // listening yet - only that some past run wrote it. Confirmed by hand:
  // without this probe, the renderer's first request could still lose
  // the race with ECONNREFUSED even after the token-write-ordering fix
  // in services/core/src/server.ts. Poll the port directly instead.
  while (Date.now() - start < timeoutMs) {
    try {
      await fetch(CORE_BASE);
      return token;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  throw new Error(`core service never answered at ${CORE_BASE} within ${timeoutMs}ms`);
}

async function coreFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${CORE_BASE}${path}`, {
    ...init,
    headers: { ...init?.headers, "X-Jarvis-Token": coreToken },
  });
}

// Same shape as waitForCoreToken, pointed at the voice sidecar's own
// token file (services/voice/voice_service.py's _load_or_create_token).
// Shorter timeout and a swallowed failure: voice is optional, unlike
// core - the app must not hang waiting for a sidecar that may not have
// its Python deps installed yet.
async function waitForVoiceToken(timeoutMs = 5_000): Promise<string> {
  const tokenPath = join(resolveDataDir(), "voice_token.txt");
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (existsSync(tokenPath)) {
      const token = readFileSync(tokenPath, "utf8").trim();
      try {
        await fetch(VOICE_BASE, { signal: AbortSignal.timeout(500) });
        return token;
      } catch {
        // token file written but server not answering yet - keep polling
      }
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`voice service never answered at ${VOICE_BASE} within ${timeoutMs}ms`);
}

async function voiceFetch(path: string, init?: RequestInit): Promise<Response> {
  if (!voiceToken) throw new Error("voice service is not available");
  return fetch(`${VOICE_BASE}${path}`, {
    ...init,
    headers: { ...init?.headers, "X-Jarvis-Token": voiceToken },
  });
}

function createWindow(): void {
  // Content Security Policy: no remote scripts, no inline eval. Renderer
  // only ever talks to the app via the preload bridge, never fetch()
  // directly to the core service (it doesn't have the token).
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": ["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"],
      },
    });
  });

  const win = new BrowserWindow({
    width: 900,
    height: 700,
    webPreferences: {
      // preload.ts compiles to preload.cjs, not preload.js: Electron's
      // sandboxed preload loader requires CommonJS, so that file is
      // built separately as CommonJS regardless of the rest of the app
      // being ESM. See src/preload.cts's own comment for why.
      preload: join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Register IPC handlers before loadFile: the renderer's first
  // getSetupStatus() call fires as soon as its script runs, and if that
  // race is lost, ipcRenderer.invoke rejects with "no handler registered"
  // before anything is listening for the rejection - the setup banner
  // then silently never updates. Confirmed by hand on Marky's machine:
  // this was the second reason the chat UI looked dead alongside the
  // preload.cts fix.
  ipcMain.handle("setup:get", async () => {
    const res = await coreFetch("/api/setup");
    return res.json();
  });

  ipcMain.handle("chat:send", async (_event, history) => {
    const res = await coreFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history }),
    });
    const jobId = res.headers.get("X-Jarvis-Job-Id") ?? "";
    // Stream SSE events to the renderer as they arrive.
    void pipeSse(res, win, jobId);
    return { jobId };
  });

  ipcMain.handle("chat:cancel", async (_event, jobId: string) => {
    await coreFetch(`/api/chat/${jobId}/cancel`, { method: "POST" });
    return { cancelled: true };
  });

  // Voice IPC: thin proxies to the sidecar's own HTTP API (see
  // services/voice/voice_service.py). The renderer drives the sequence
  // (start on press, stop on release, feed the transcript into the
  // existing chat:send flow, speak the reply once it's done) - this
  // process only forwards requests and surfaces real errors, it never
  // fakes a transcript or a spoken reply that didn't happen.
  ipcMain.handle("voice:pttStart", async () => {
    const res = await voiceFetch("/ptt/start", { method: "POST" });
    return res.json();
  });

  ipcMain.handle("voice:pttStop", async () => {
    const res = await voiceFetch("/ptt/stop", { method: "POST" });
    return res.json();
  });

  ipcMain.handle("voice:speak", async (_event, text: string) => {
    const res = await voiceFetch("/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    return res.json();
  });

  win.loadFile(join(__dirname, "..", "index.html"));
}

async function pipeSse(res: Response, win: BrowserWindow, jobId: string): Promise<void> {
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const raw of events) {
      const eventLine = raw.split("\n").find((l) => l.startsWith("event: "));
      const dataLine = raw.split("\n").find((l) => l.startsWith("data: "));
      if (!eventLine || !dataLine) continue;
      const eventName = eventLine.slice("event: ".length);
      const data = JSON.parse(dataLine.slice("data: ".length));
      win.webContents.send(`chat:${eventName}`, data);
    }
  }
}

app.whenReady().then(async () => {
  startCore();
  startVoice();
  [coreToken, voiceToken] = await Promise.all([
    waitForCoreToken().catch((err) => {
      console.error(err);
      return "";
    }),
    waitForVoiceToken().catch((err) => {
      console.error(`voice unavailable: ${err.message}`);
      return "";
    }),
  ]);
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  coreProcess?.kill();
  voiceProcess?.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  coreProcess?.kill();
  voiceProcess?.kill();
});

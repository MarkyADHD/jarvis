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

function resolveDataDir(): string {
  if (process.env.JARVIS_DATA_DIR) return process.env.JARVIS_DATA_DIR;
  if (process.platform === "win32" && existsSync("E:\\")) return "E:\\Jarvis\\data";
  return join(__dirname, "..", "..", "..", ".data");
}

let coreProcess: ChildProcess | undefined;
let coreToken = "";

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

async function waitForCoreToken(timeoutMs = 10_000): Promise<string> {
  const tokenPath = join(resolveDataDir(), "core-token");
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (existsSync(tokenPath)) return readFileSync(tokenPath, "utf8").trim();
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`core-token never appeared at ${tokenPath} - is the core service running?`);
}

async function coreFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${CORE_BASE}${path}`, {
    ...init,
    headers: { ...init?.headers, "X-Jarvis-Token": coreToken },
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
  win.loadFile(join(__dirname, "..", "index.html"));

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
  coreToken = await waitForCoreToken().catch((err) => {
    console.error(err);
    return "";
  });
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  coreProcess?.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  coreProcess?.kill();
});

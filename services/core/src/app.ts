/**
 * The HTTP surface, factored out from process wiring (token file, DB
 * path, `.listen()`) so it can be unit-tested with in-memory
 * dependencies. See src/server.ts for the real entrypoint.
 */

import { createServer, type IncomingMessage, type ServerResponse, type Server } from "node:http";
import { randomUUID } from "node:crypto";
import type { ClaudeRuntime } from "@jarvis/claude-runtime";
import type { ChatMessage, Job } from "@jarvis/contracts";
import type { JobStore } from "./db.js";

export interface AppDeps {
  claude: ClaudeRuntime;
  jobs: JobStore;
  authToken: string;
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const data = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) });
  res.end(data);
}

async function readJsonBody<T>(req: IncomingMessage): Promise<T> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? (JSON.parse(raw) as T) : ({} as T);
}

export function createApp(deps: AppDeps): Server {
  const { claude, jobs, authToken } = deps;
  const activeStreams = new Map<string, AbortController>();

  async function handleChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const body = await readJsonBody<{ history: ChatMessage[] }>(req);
    const history = body.history ?? [];
    const lastUser = history[history.length - 1];
    if (!lastUser || lastUser.role !== "user") {
      return sendJson(res, 400, { error: "history must end with a user message" });
    }

    const jobId = randomUUID();
    const now = new Date().toISOString();
    const job: Job = {
      id: jobId,
      goal: lastUser.text.slice(0, 200),
      origin: "owner-desktop",
      state: "running",
      createdAt: now,
      updatedAt: now,
      steps: [],
    };
    jobs.create(job);

    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Jarvis-Job-Id": jobId,
    });

    const controller = new AbortController();
    activeStreams.set(jobId, controller);
    req.on("close", () => controller.abort());

    const send = (event: string, data: unknown) => {
      res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    };

    try {
      const gen = claude.streamChat(history, { jobId, signal: controller.signal });
      let next = await gen.next();
      while (!next.done) {
        send("delta", next.value);
        next = await gen.next();
      }
      const finalMessage = next.value;
      jobs.updateState(jobId, "succeeded", {
        outcome: "succeeded",
        summary: finalMessage.text.slice(0, 200),
      });
      send("done", { jobId, message: finalMessage });
    } catch (err) {
      const aborted = controller.signal.aborted;
      jobs.updateState(jobId, aborted ? "cancelled" : "failed", {
        outcome: aborted ? "unknown" : "failed",
        summary: aborted ? "Cancelled by user." : err instanceof Error ? err.message : String(err),
      });
      send(aborted ? "cancelled" : "error", {
        jobId,
        message: aborted ? "cancelled" : err instanceof Error ? err.message : String(err),
      });
    } finally {
      activeStreams.delete(jobId);
      res.end();
    }
  }

  return createServer(async (req, res) => {
    try {
      if (!req.url) return sendJson(res, 400, { error: "bad request" });
      const url = new URL(req.url, "http://localhost");

      if (req.headers["x-jarvis-token"] !== authToken) {
        return sendJson(res, 401, { error: "missing or invalid X-Jarvis-Token" });
      }

      if (req.method === "GET" && url.pathname === "/api/setup") {
        return sendJson(res, 200, claude.getSetupStatus());
      }

      if (req.method === "GET" && url.pathname === "/api/jobs") {
        return sendJson(res, 200, { jobs: jobs.list() });
      }

      const jobMatch = url.pathname.match(/^\/api\/jobs\/([^/]+)$/);
      if (req.method === "GET" && jobMatch) {
        const job = jobs.get(jobMatch[1]);
        return job ? sendJson(res, 200, job) : sendJson(res, 404, { error: "not found" });
      }

      if (req.method === "POST" && url.pathname === "/api/chat") {
        return await handleChat(req, res);
      }

      const cancelMatch = url.pathname.match(/^\/api\/chat\/([^/]+)\/cancel$/);
      if (req.method === "POST" && cancelMatch) {
        const controller = activeStreams.get(cancelMatch[1]);
        if (!controller) return sendJson(res, 404, { error: "no active stream for that job" });
        controller.abort();
        return sendJson(res, 202, { cancelled: true });
      }

      sendJson(res, 404, { error: "not found" });
    } catch (err) {
      sendJson(res, 500, { error: err instanceof Error ? err.message : String(err) });
    }
  });
}

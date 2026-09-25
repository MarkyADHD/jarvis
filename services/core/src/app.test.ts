import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ClaudeRuntime } from "@jarvis/claude-runtime";
import { createApp } from "./app.js";
import { JobStore } from "./db.js";

const AUTH_TOKEN = "test-token";
let dir: string;
let jobs: JobStore;
let server: ReturnType<typeof createApp>;
let baseUrl: string;

beforeEach(async () => {
  dir = mkdtempSync(join(tmpdir(), "jarvis-core-app-test-"));
  jobs = new JobStore(join(dir, "test.db"));
  const claude = new ClaudeRuntime({ apiKey: undefined }); // no key: honest not-configured path
  server = createApp({ claude, jobs, authToken: AUTH_TOKEN });
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const port = (server.address() as AddressInfo).port;
  baseUrl = `http://127.0.0.1:${port}`;
});

afterEach(async () => {
  await new Promise((resolve) => server.close(resolve));
  jobs.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("core HTTP API", () => {
  it("rejects requests without a valid token", async () => {
    const res = await fetch(`${baseUrl}/api/setup`);
    expect(res.status).toBe(401);
  });

  it("reports Claude as not-configured truthfully", async () => {
    const res = await fetch(`${baseUrl}/api/setup`, {
      headers: { "X-Jarvis-Token": AUTH_TOKEN },
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { claude: { state: string } };
    expect(body.claude.state).toBe("not-configured");
  });

  it("returns a real error over chat instead of a fake reply when not configured", async () => {
    const res = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "X-Jarvis-Token": AUTH_TOKEN, "Content-Type": "application/json" },
      body: JSON.stringify({
        history: [{ id: "1", role: "user", text: "hello", createdAt: new Date().toISOString() }],
      }),
    });
    expect(res.status).toBe(200); // SSE stream opens...
    const text = await res.text();
    expect(text).toContain("event: error"); // ...but it truthfully reports the error, no fake answer
    expect(text).not.toContain("event: done");
  });

  it("rejects chat requests with no trailing user message", async () => {
    const res = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "X-Jarvis-Token": AUTH_TOKEN, "Content-Type": "application/json" },
      body: JSON.stringify({ history: [] }),
    });
    expect(res.status).toBe(400);
  });

  it("404s a cancel request for an unknown job rather than pretending it worked", async () => {
    const res = await fetch(`${baseUrl}/api/chat/does-not-exist/cancel`, {
      method: "POST",
      headers: { "X-Jarvis-Token": AUTH_TOKEN },
    });
    expect(res.status).toBe(404);
  });
});

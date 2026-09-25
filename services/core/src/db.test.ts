import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { JobStore } from "./db.js";
import type { Job } from "@jarvis/contracts";

let dir: string;
let store: JobStore;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "jarvis-core-test-"));
  store = new JobStore(join(dir, "test.db"));
});

afterEach(() => {
  store.close();
  rmSync(dir, { recursive: true, force: true });
});

function makeJob(id: string): Job {
  const now = new Date().toISOString();
  return {
    id,
    goal: "say hello",
    origin: "owner-desktop",
    state: "running",
    createdAt: now,
    updatedAt: now,
    steps: [],
  };
}

describe("JobStore", () => {
  it("persists and retrieves a job", () => {
    store.create(makeJob("job-1"));
    const job = store.get("job-1");
    expect(job?.goal).toBe("say hello");
    expect(job?.state).toBe("running");
  });

  it("updates state and result without fabricating success", () => {
    store.create(makeJob("job-2"));
    store.updateState("job-2", "failed", { outcome: "failed", summary: "connection refused" });
    const job = store.get("job-2");
    expect(job?.state).toBe("failed");
    expect(job?.result?.outcome).toBe("failed");
    expect(job?.result?.summary).toBe("connection refused");
  });

  it("appends steps in order", () => {
    store.create(makeJob("job-3"));
    store.appendStep("job-3", { id: "s1", description: "planned" });
    store.appendStep("job-3", { id: "s2", description: "executed" });
    const job = store.get("job-3");
    expect(job?.steps.map((s) => s.id)).toEqual(["s1", "s2"]);
  });

  it("lists jobs newest first", () => {
    store.create(makeJob("job-a"));
    store.create({ ...makeJob("job-b"), createdAt: new Date(Date.now() + 1000).toISOString() });
    const list = store.list();
    expect(list[0].id).toBe("job-b");
  });

  it("survives a restart (recovers state from disk)", () => {
    const dbPath = join(dir, "restart.db");
    const first = new JobStore(dbPath);
    first.create(makeJob("job-r"));
    first.close();

    const second = new JobStore(dbPath);
    const job = second.get("job-r");
    expect(job?.id).toBe("job-r");
    second.close();
  });
});

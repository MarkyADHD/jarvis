import { describe, expect, it } from "vitest";
import { ClaudeNotConfiguredError, ClaudeRuntime } from "./index.js";

describe("ClaudeRuntime setup status", () => {
  it("reports not-configured honestly when there is no API key", () => {
    const runtime = new ClaudeRuntime({ apiKey: undefined });
    const status = runtime.getSetupStatus();
    expect(status.claude.state).toBe("not-configured");
    expect(status.claude.detail).toMatch(/ANTHROPIC_API_KEY/);
  });

  it("reports connected when a key is present", () => {
    const runtime = new ClaudeRuntime({ apiKey: "sk-ant-test-not-real" });
    const status = runtime.getSetupStatus();
    expect(status.claude.state).toBe("connected");
  });

  it("throws ClaudeNotConfiguredError instead of pretending to answer", async () => {
    const runtime = new ClaudeRuntime({ apiKey: undefined });
    const gen = runtime.streamChat(
      [{ id: "1", role: "user", text: "hi", createdAt: new Date().toISOString() }],
      { jobId: "job-1" }
    );
    await expect(gen.next()).rejects.toBeInstanceOf(ClaudeNotConfiguredError);
  });
});

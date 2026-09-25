import { describe, expect, it } from "vitest";
import { ClaudeNotConfiguredError, ClaudeRuntime } from "./index.js";

// Deliberately not a real path, so detectCli() reliably fails without
// depending on whether a `claude` binary happens to exist in whatever
// environment runs this test.
const NO_SUCH_CLI = "definitely-not-a-real-claude-cli-binary";

describe("ClaudeRuntime backend selection", () => {
  it("auto-detects the cli backend when the `claude` binary is on PATH", () => {
    // This sandbox genuinely has Claude Code installed - exercising the
    // real detection path Marky's own machine will hit, not a mock.
    const runtime = new ClaudeRuntime({ apiKey: undefined, cliBin: "claude" });
    const status = runtime.getSetupStatus();
    expect(status.claude.state).toBe("connected");
    expect(status.claude.detail).toMatch(/claude` CLI already logged in/);
  });

  it("falls back to not-configured with neither a CLI nor a key", () => {
    const runtime = new ClaudeRuntime({ apiKey: undefined, cliBin: NO_SUCH_CLI });
    const status = runtime.getSetupStatus();
    expect(status.claude.state).toBe("not-configured");
    expect(status.claude.detail).toMatch(/ANTHROPIC_API_KEY/);
  });

  it("falls back to the api key when no CLI is present", () => {
    const runtime = new ClaudeRuntime({ apiKey: "sk-ant-test-not-real", cliBin: NO_SUCH_CLI });
    const status = runtime.getSetupStatus();
    expect(status.claude.state).toBe("connected");
  });

  it("prefers the CLI over an API key when both are available", () => {
    const runtime = new ClaudeRuntime({ apiKey: "sk-ant-test-not-real", cliBin: "claude" });
    expect(runtime.getSetupStatus().claude.detail).toMatch(/CLI already logged in/);
  });

  it("throws ClaudeNotConfiguredError instead of pretending to answer", async () => {
    const runtime = new ClaudeRuntime({ apiKey: undefined, cliBin: NO_SUCH_CLI });
    const gen = runtime.streamChat(
      [{ id: "1", role: "user", text: "hi", createdAt: new Date().toISOString() }],
      { jobId: "job-1" }
    );
    await expect(gen.next()).rejects.toBeInstanceOf(ClaudeNotConfiguredError);
  });
});

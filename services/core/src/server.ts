/**
 * Real entrypoint: wires actual dependencies (token file, SQLite path,
 * env-configured Claude runtime) and starts listening. The testable
 * HTTP surface itself lives in src/app.ts.
 */

import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ClaudeRuntime } from "@jarvis/claude-runtime";
import { createApp } from "./app.js";
import { JobStore, resolveDataDir } from "./db.js";

const PORT = Number(process.env.JARVIS_CORE_PORT ?? 8765);
const dataDir = resolveDataDir();
if (!existsSync(dataDir)) mkdirSync(dataDir, { recursive: true });

function loadOrCreateToken(path: string): string {
  if (existsSync(path)) return readFileSync(path, "utf8").trim();
  return randomBytes(24).toString("hex");
}

const tokenPath = join(dataDir, "core-token");
const authToken = loadOrCreateToken(tokenPath);
const jobs = new JobStore(join(dataDir, "jarvis.db"));
const claude = ClaudeRuntime.fromEnv();

const server = createApp({ claude, jobs, authToken });

server.listen(PORT, () => {
  // Write the token file only once the server is actually accepting
  // connections, not at module load. Electron's main process polls for
  // this file to know when the core service is ready before creating
  // its window; writing it earlier let that poll succeed before
  // listen() had actually bound the port, so the renderer's first
  // /api/setup request could lose the race with ECONNREFUSED. Confirmed
  // by hand on Marky's machine - this is what caused it, not a guess.
  writeFileSync(tokenPath, authToken, { mode: 0o600 });
  // eslint-disable-next-line no-console
  console.log(`jarvis core listening on http://localhost:${PORT} (data: ${dataDir})`);
  // eslint-disable-next-line no-console
  console.log(`auth token file: ${tokenPath}`);
});

export { server };

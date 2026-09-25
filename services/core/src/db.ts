/**
 * Job persistence. SQLite via Node's built-in `node:sqlite` (experimental,
 * but avoids a native-compile dependency like better-sqlite3 for this
 * first slice - revisit if node:sqlite's experimental status becomes a
 * real blocker, per docs/architecture.md's SQLite+FTS5 decision).
 *
 * One database file. Default location follows CLAUDE.md's existing
 * preference: `E:\Jarvis\data` on the real machine when available,
 * falling back to a local `.data` directory (this container has no E:,
 * and that's fine - see docs/architecture.md's "where this runs" note).
 */

import { DatabaseSync } from "node:sqlite";
import { existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { Job, JobState, JobStep } from "@jarvis/contracts";

export function resolveDataDir(): string {
  if (process.env.JARVIS_DATA_DIR) return process.env.JARVIS_DATA_DIR;
  if (process.platform === "win32" && existsSync("E:\\")) return "E:\\Jarvis\\data";
  return new URL("../../../.data", import.meta.url).pathname;
}

export class JobStore {
  private readonly db: DatabaseSync;

  constructor(dbPath: string) {
    const dir = dirname(dbPath);
    if (dir && !existsSync(dir)) mkdirSync(dir, { recursive: true });
    this.db = new DatabaseSync(dbPath);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        origin TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        steps_json TEXT NOT NULL,
        cost_json TEXT,
        result_json TEXT
      );
    `);
  }

  create(job: Job): void {
    this.db
      .prepare(
        `INSERT INTO jobs (id, goal, origin, state, created_at, updated_at, steps_json, cost_json, result_json)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        job.id,
        job.goal,
        job.origin,
        job.state,
        job.createdAt,
        job.updatedAt,
        JSON.stringify(job.steps),
        job.cost ? JSON.stringify(job.cost) : null,
        job.result ? JSON.stringify(job.result) : null
      );
  }

  updateState(id: string, state: JobState, result?: Job["result"]): void {
    this.db
      .prepare(`UPDATE jobs SET state = ?, updated_at = ?, result_json = ? WHERE id = ?`)
      .run(state, new Date().toISOString(), result ? JSON.stringify(result) : null, id);
  }

  appendStep(id: string, step: JobStep): void {
    const row = this.get(id);
    if (!row) return;
    const steps = [...row.steps, step];
    this.db
      .prepare(`UPDATE jobs SET steps_json = ?, updated_at = ? WHERE id = ?`)
      .run(JSON.stringify(steps), new Date().toISOString(), id);
  }

  get(id: string): Job | undefined {
    const row = this.db.prepare(`SELECT * FROM jobs WHERE id = ?`).get(id) as
      | Record<string, unknown>
      | undefined;
    return row ? rowToJob(row) : undefined;
  }

  list(limit = 50): Job[] {
    const rows = this.db
      .prepare(`SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?`)
      .all(limit) as Record<string, unknown>[];
    return rows.map(rowToJob);
  }

  close(): void {
    this.db.close();
  }
}

function rowToJob(row: Record<string, unknown>): Job {
  return {
    id: row.id as string,
    goal: row.goal as string,
    origin: row.origin as Job["origin"],
    state: row.state as JobState,
    createdAt: row.created_at as string,
    updatedAt: row.updated_at as string,
    steps: JSON.parse((row.steps_json as string) ?? "[]"),
    cost: row.cost_json ? JSON.parse(row.cost_json as string) : undefined,
    result: row.result_json ? JSON.parse(row.result_json as string) : undefined,
  };
}

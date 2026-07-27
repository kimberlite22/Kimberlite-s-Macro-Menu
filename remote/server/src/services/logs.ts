import { and, asc, eq, gt, sql } from "drizzle-orm";
import type { Database } from "../db/types.js";
import { logs } from "../db/schema.js";
import { env } from "../env.js";

export interface LogLineInput {
  readonly seq: number;
  readonly line: string;
}

export interface AppendLogsInput {
  readonly deviceId: string;
  readonly userId: string;
  readonly lines: readonly LogLineInput[];
}

/** Inserts agent log lines idempotently, keyed by the device's monotonic sequence number. */
export async function appendLogs(database: Database, input: AppendLogsInput): Promise<number> {
  if (input.lines.length === 0) return 0;
  const inserted = await database
    .insert(logs)
    .values(input.lines.map((entry) => ({
      deviceId: input.deviceId,
      userId: input.userId,
      seq: entry.seq,
      line: entry.line,
    })))
    .onConflictDoNothing({ target: [logs.deviceId, logs.seq] })
    .returning({ id: logs.id });

  // Best-effort retention: keep only the newest LOG_MAX_PER_DEVICE rows for this device so logs stay
  // bounded. Raw SQL keeps it a single round-trip and works on both PGlite and node-postgres.
  if (inserted.length > 0) {
    await database.execute(sql`
      delete from logs
      where device_id = ${input.deviceId}
        and id not in (
          select id from logs
          where device_id = ${input.deviceId}
          order by id desc
          limit ${env.LOG_MAX_PER_DEVICE}
        )
    `);
  }
  return inserted.length;
}

export interface GetLogsSinceInput {
  readonly deviceId: string;
  /** The backend row id the browser last observed; omit or 0 to read from the beginning. */
  readonly sinceId?: number;
  readonly limit?: number;
}

export interface LogPage {
  readonly lines: ReadonlyArray<{
    readonly id: number;
    readonly seq: number;
    readonly line: string;
    readonly receivedAt: Date;
  }>;
  readonly lastId: number;
}

/** Fetches a stable, id-ordered page after the browser's last observed backend row id. */
export async function getLogsSince(database: Database, input: GetLogsSinceInput): Promise<LogPage> {
  const sinceId = input.sinceId === undefined ? 0 : Math.max(0, Math.floor(input.sinceId));
  const requestedLimit = input.limit ?? 200;
  const limit = Math.min(1000, Math.max(1, Math.floor(requestedLimit)));
  const lines = await database
    .select({ id: logs.id, seq: logs.seq, line: logs.line, receivedAt: logs.receivedAt })
    .from(logs)
    .where(and(eq(logs.deviceId, input.deviceId), gt(logs.id, sinceId)))
    .orderBy(asc(logs.id))
    .limit(limit);
  return { lines, lastId: lines.at(-1)?.id ?? sinceId };
}

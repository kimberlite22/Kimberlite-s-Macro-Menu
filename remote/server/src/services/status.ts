import { desc, eq } from "drizzle-orm";
import type { Database } from "../db/types.js";
import { deviceStatus, deviceSessions } from "../db/schema.js";

export interface UpsertStatusInput {
  readonly deviceId: string;
  readonly userId: string;
  readonly snapshot: Record<string, unknown>;
  readonly macroOnline: boolean;
  readonly macroTimestamp?: string;
}

/**
 * If the incoming snapshot carries a `sessionId` that differs from the device's currently stored
 * one, the stored snapshot is the previous session's last-known state - archive it into
 * `device_sessions` before it gets overwritten below. This is the only place a session boundary is
 * detected; the agent and macro have no session-aware logic of their own (see PROTOCOL.md section 5).
 */
async function archivePreviousSessionIfChanged(
  database: Database,
  input: UpsertStatusInput,
): Promise<void> {
  const incomingSessionId = input.snapshot.sessionId;
  if (typeof incomingSessionId !== "string" || incomingSessionId === "") {
    return;
  }
  const previous = await getStatus(database, input.deviceId);
  if (!previous || typeof previous.snapshotJson !== "object" || previous.snapshotJson === null) {
    return;
  }
  const previousSessionId = (previous.snapshotJson as Record<string, unknown>).sessionId;
  if (typeof previousSessionId !== "string" || previousSessionId === "" || previousSessionId === incomingSessionId) {
    return;
  }
  // onConflictDoNothing on (deviceId, sessionId): two overlapping reports for the same device can
  // both observe the same stale device_status row and both try to archive it here - the unique
  // index makes that a harmless no-op instead of a duplicate history row (same pattern as
  // logs.appendLogs's (deviceId, seq) idempotency).
  await database
    .insert(deviceSessions)
    .values({
      deviceId: previous.deviceId,
      userId: previous.userId,
      sessionId: previousSessionId,
      snapshotJson: previous.snapshotJson,
      endedAt: previous.receivedAt,
    })
    .onConflictDoNothing({ target: [deviceSessions.deviceId, deviceSessions.sessionId] });
}

/** Stores the latest agent status snapshot for a device. */
export async function upsertStatus(database: Database, input: UpsertStatusInput): Promise<void> {
  await archivePreviousSessionIfChanged(database, input);

  const values = {
    ...input,
    snapshotJson: input.snapshot,
    receivedAt: new Date(),
  };
  await database
    .insert(deviceStatus)
    .values(values)
    .onConflictDoUpdate({
      target: deviceStatus.deviceId,
      set: values,
    });
}

/** Returns persisted session history for a device, most recent first. */
export async function listSessions(database: Database, deviceId: string, limit = 50) {
  return database
    .select()
    .from(deviceSessions)
    .where(eq(deviceSessions.deviceId, deviceId))
    .orderBy(desc(deviceSessions.id))
    .limit(limit);
}

/** Returns the most recently stored status for a device. */
export async function getStatus(database: Database, deviceId: string) {
  const [status] = await database.select().from(deviceStatus).where(eq(deviceStatus.deviceId, deviceId)).limit(1);
  return status ?? null;
}

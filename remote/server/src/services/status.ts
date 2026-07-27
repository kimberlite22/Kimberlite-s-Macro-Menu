import { eq } from "drizzle-orm";
import type { Database } from "../db/types.js";
import { deviceStatus } from "../db/schema.js";

export interface UpsertStatusInput {
  readonly deviceId: string;
  readonly userId: string;
  readonly snapshot: Record<string, unknown>;
  readonly macroOnline: boolean;
  readonly macroTimestamp?: string;
}

/** Stores the latest agent status snapshot for a device. */
export async function upsertStatus(database: Database, input: UpsertStatusInput): Promise<void> {
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

/** Returns the most recently stored status for a device. */
export async function getStatus(database: Database, deviceId: string) {
  const [status] = await database.select().from(deviceStatus).where(eq(deviceStatus.deviceId, deviceId)).limit(1);
  return status ?? null;
}

import { randomUUID } from "node:crypto";
import { and, desc, eq, isNull } from "drizzle-orm";
import type { Database } from "../db/types.js";
import { devices } from "../db/schema.js";

export interface CreateDeviceInput {
  readonly userId: string;
  readonly name: string;
  readonly tokenHash: string;
  readonly hostname?: string;
  readonly os?: string;
  readonly agentVersion?: string;
}

/** Creates a device whose token has already been hashed by the security layer. */
export async function createDevice(database: Database, input: CreateDeviceInput) {
  const [device] = await database.insert(devices).values({ id: randomUUID(), ...input }).returning();
  if (device === undefined) throw new Error("Failed to create device.");
  return device;
}

/** Finds a non-revoked device by its stored token hash. */
export async function findActiveByTokenHash(database: Database, tokenHash: string) {
  const [device] = await database
    .select()
    .from(devices)
    .where(and(eq(devices.tokenHash, tokenHash), isNull(devices.revokedAt)))
    .limit(1);
  return device ?? null;
}

/** Lists a user's devices with the newest device first. */
export async function listByUser(database: Database, userId: string) {
  return database.select().from(devices).where(eq(devices.userId, userId)).orderBy(desc(devices.createdAt));
}

/** Returns a device only when it belongs to the supplied tenant. */
export async function getOwned(database: Database, userId: string, deviceId: string) {
  const [device] = await database
    .select()
    .from(devices)
    .where(and(eq(devices.id, deviceId), eq(devices.userId, userId)))
    .limit(1);
  return device ?? null;
}

/** Revokes a user's device. Returns false for a missing or foreign device. */
export async function revoke(database: Database, userId: string, deviceId: string): Promise<boolean> {
  const updated = await database
    .update(devices)
    .set({ revokedAt: new Date() })
    .where(and(eq(devices.id, deviceId), eq(devices.userId, userId)))
    .returning({ id: devices.id });
  return updated.length > 0;
}

/** Records a successful authenticated contact from the device. */
export async function touchLastSeen(database: Database, deviceId: string): Promise<void> {
  await database.update(devices).set({ lastSeenAt: new Date() }).where(eq(devices.id, deviceId));
}

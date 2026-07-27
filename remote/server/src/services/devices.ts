import { randomUUID } from "node:crypto";
import { and, desc, eq, gt, isNull } from "drizzle-orm";
import type { Database } from "../db/types.js";
import { devices, pairingCodes } from "../db/schema.js";

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

/** Returns a non-revoked device by id (used to re-check liveness during a long-poll), else null. */
export async function findActiveById(database: Database, deviceId: string) {
  const [device] = await database
    .select()
    .from(devices)
    .where(and(eq(devices.id, deviceId), isNull(devices.revokedAt)))
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

export interface CreatePairingCodeInput {
  readonly userId: string;
  readonly deviceName?: string;
  readonly codeHash: string;
  readonly expiresAt: Date;
}

/** Stores a previously hashed pairing code. Plaintext codes never enter this layer. */
export async function createPairingCode(database: Database, input: CreatePairingCodeInput) {
  const [pairingCode] = await database
    .insert(pairingCodes)
    .values({ id: randomUUID(), ...input })
    .returning();
  if (pairingCode === undefined) throw new Error("Failed to create pairing code.");
  return pairingCode;
}

export interface RedeemedPairingCode {
  readonly userId: string;
  readonly deviceName: string | null;
}

/**
 * Atomically consumes one unexpired pairing code. The row lock plus used-at predicate ensures that
 * concurrent attempts can produce at most one successful redemption.
 */
export async function redeemPairingCode(
  database: Database,
  codeHash: string,
): Promise<RedeemedPairingCode | null> {
  return database.transaction(async (tx) => {
    const now = new Date();
    const [candidate] = await tx
      .select()
      .from(pairingCodes)
      .where(and(
        eq(pairingCodes.codeHash, codeHash),
        isNull(pairingCodes.usedAt),
        gt(pairingCodes.expiresAt, now),
      ))
      .limit(1)
      .for("update");

    if (candidate === undefined) return null;

    const [redeemed] = await tx
      .update(pairingCodes)
      .set({ usedAt: now })
      .where(and(eq(pairingCodes.id, candidate.id), isNull(pairingCodes.usedAt)))
      .returning({ userId: pairingCodes.userId, deviceName: pairingCodes.deviceName });

    return redeemed ?? null;
  });
}

export interface RedeemAndCreateDeviceInput {
  readonly codeHash: string;
  readonly tokenHash: string;
  readonly hostname?: string;
  readonly os?: string;
  readonly agentVersion?: string;
}

/**
 * Redeems a pairing code AND creates the device in one transaction, so the code is consumed ONLY
 * when device creation also succeeds: if the insert fails the whole transaction rolls back and the
 * code stays usable. The row lock plus the used-at predicate keep redemption single-use under
 * concurrency. Returns the new device, or null when the code is missing, already used, or expired.
 */
export async function redeemPairingCodeAndCreateDevice(
  database: Database,
  input: RedeemAndCreateDeviceInput,
) {
  return database.transaction(async (tx) => {
    const now = new Date();
    const [candidate] = await tx
      .select()
      .from(pairingCodes)
      .where(and(
        eq(pairingCodes.codeHash, input.codeHash),
        isNull(pairingCodes.usedAt),
        gt(pairingCodes.expiresAt, now),
      ))
      .limit(1)
      .for("update");

    if (candidate === undefined) return null;

    const [redeemed] = await tx
      .update(pairingCodes)
      .set({ usedAt: now })
      .where(and(eq(pairingCodes.id, candidate.id), isNull(pairingCodes.usedAt)))
      .returning({ userId: pairingCodes.userId, deviceName: pairingCodes.deviceName });

    if (redeemed === undefined) return null;

    const [device] = await tx
      .insert(devices)
      .values({
        id: randomUUID(),
        userId: redeemed.userId,
        name: redeemed.deviceName || input.hostname || "device",
        tokenHash: input.tokenHash,
        hostname: input.hostname,
        os: input.os,
        agentVersion: input.agentVersion,
      })
      .returning();

    if (device === undefined) throw new Error("Failed to create device.");
    return device;
  });
}

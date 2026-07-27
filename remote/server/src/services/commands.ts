import { randomUUID } from "node:crypto";
import { and, asc, eq, inArray, lt, or } from "drizzle-orm";
import type { CommandType } from "../shared/commands.js";
import { validateCommand } from "../shared/commands.js";
import type { Database } from "../db/types.js";
import { commands, devices } from "../db/schema.js";
import { deviceNotifier } from "../lib/longpoll.js";
import { env } from "../env.js";
import { getOwned } from "./devices.js";

/** A validation failure that the HTTP layer may map directly to a 400 response. */
export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

export interface EnqueueInput {
  readonly userId: string;
  readonly deviceId: string;
  readonly type: unknown;
  readonly arg?: unknown;
}

/** Validates and queues a browser command for a device owned by the requesting user. */
export async function enqueue(database: Database, input: EnqueueInput): Promise<{ commandId: string }> {
  const validation = validateCommand({ type: input.type, arg: input.arg });
  if (!validation.ok) throw new ValidationError(validation.error ?? "Invalid command.");
  const device = await getOwned(database, input.userId, input.deviceId);
  if (device === null) {
    throw new Error("Device does not exist or is not owned by this user.");
  }
  // Defense in depth against a revoke racing this enqueue: a revoked device can never authenticate
  // again, so it would never fetch the command. (The route also rejects revoked devices up front.)
  if (device.revokedAt !== null) {
    throw new ValidationError("Device is revoked.");
  }

  const commandId = randomUUID();
  await database.insert(commands).values({
    id: commandId,
    userId: input.userId,
    deviceId: input.deviceId,
    type: input.type as CommandType,
    arg: typeof input.arg === "string" ? input.arg : "",
    status: "pending",
  });
  deviceNotifier.notify(input.deviceId);
  return { commandId };
}

export interface Command {
  readonly id: string;
  readonly type: CommandType;
  readonly arg: string;
}

/**
 * Claims a small oldest-first batch for the agent's long-poll. Delivery is at-least-once: besides
 * `pending` commands, it reclaims commands that were `delivered` but never acked within the lease
 * window (a dropped long-poll response, or an agent crash between apply and ack), and it expires
 * commands left unacked past COMMAND_MAX_AGE_SECONDS so an offline device does not accumulate an
 * unbounded redelivery backlog. Redelivery is safe: the agent tags remote_cmd.txt with the command
 * id and the macro ignores a repeated token, so an already-applied command is never applied twice,
 * and the agent re-acks it, which moves it out of the redelivery set.
 */
export async function takePending(database: Database, deviceId: string): Promise<Command[]> {
  const now = new Date();
  const leaseCutoff = new Date(now.getTime() - env.COMMAND_LEASE_SECONDS * 1000);
  const ageCutoff = new Date(now.getTime() - env.COMMAND_MAX_AGE_SECONDS * 1000);

  return database.transaction(async (tx) => {
    // Atomically gate on revocation: lock the device row FOR UPDATE so a concurrent revoke cannot
    // interleave between this check and the command claim below (TOCTOU). A revoked or missing device
    // claims nothing, so a device revoked at any point before this transaction commits gets no
    // commands. This is the authoritative delivery gate (the routes' revoked checks are fast-paths).
    const [device] = await tx
      .select({ revokedAt: devices.revokedAt })
      .from(devices)
      .where(eq(devices.id, deviceId))
      .limit(1)
      .for("update");
    if (device === undefined || device.revokedAt !== null) {
      return [];
    }

    // Expire unacked commands older than the max age so they stop being redelivered forever.
    await tx
      .update(commands)
      .set({ status: "expired" })
      .where(and(
        eq(commands.deviceId, deviceId),
        inArray(commands.status, ["pending", "delivered"]),
        lt(commands.createdAt, ageCutoff),
      ));

    // Claim pending commands plus delivered-but-lease-expired ones, oldest first.
    const claimable = await tx
      .select({ id: commands.id, type: commands.type, arg: commands.arg })
      .from(commands)
      .where(and(
        eq(commands.deviceId, deviceId),
        or(
          eq(commands.status, "pending"),
          and(eq(commands.status, "delivered"), lt(commands.deliveredAt, leaseCutoff)),
        ),
      ))
      .orderBy(asc(commands.createdAt))
      .limit(20)
      .for("update", { skipLocked: true });

    if (claimable.length === 0) return [];
    const commandIds = claimable.map((command) => command.id);
    // (Re)mark delivered and renew the lease clock.
    await tx
      .update(commands)
      .set({ status: "delivered", deliveredAt: now })
      .where(inArray(commands.id, commandIds));
    return claimable;
  });
}

export interface RecordAckInput {
  readonly deviceId: string;
  readonly commandId: string;
  readonly ok: boolean;
  readonly message?: string;
}

/** Records an agent acknowledgement, constrained to that agent's own device. */
export async function recordAck(database: Database, input: RecordAckInput): Promise<void> {
  await database
    .update(commands)
    .set({
      status: input.ok ? "acked" : "error",
      ok: input.ok,
      message: input.message ?? null,
      ackedAt: new Date(),
    })
    .where(and(eq(commands.id, input.commandId), eq(commands.deviceId, input.deviceId)));
}

/** Looks up a command only when both the device and tenant match. */
export async function getCommand(database: Database, userId: string, deviceId: string, commandId: string) {
  const [command] = await database
    .select()
    .from(commands)
    .where(and(
      eq(commands.id, commandId),
      eq(commands.deviceId, deviceId),
      eq(commands.userId, userId),
    ))
    .limit(1);
  return command ?? null;
}

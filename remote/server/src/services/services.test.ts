import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

// The DB directory must be selected BEFORE any module that reads env.ts is imported (env.ts is
// evaluated once, at import time). So set the environment first, then import everything that touches
// it dynamically. This keeps the test on a throwaway PGlite directory and never on the repo ./.data.
const dataDir = await mkdtemp(join(tmpdir(), "anime-expedition-server-test-"));
process.env.NODE_ENV = "test";
process.env.DATABASE_URL = "";
process.env.DATA_DIR = dataDir;

const { users } = await import("../db/schema.js");
const { hashPairingCode, newPairingCode } = await import("../security/tokens.js");
const { createDevice, createPairingCode, findActiveByTokenHash, redeemPairingCode, revoke } =
  await import("./devices.js");
const { enqueue, getCommand, recordAck, takePending } = await import("./commands.js");
const { appendLogs, getLogsSince } = await import("./logs.js");
const { db, closeDb } = await import("../db/client.js");
const { runMigrations } = await import("../db/migrate.js");

test("device, pairing, command, and log services work against PGlite", async (t) => {
  t.after(async () => {
    await closeDb();
    await rm(dataDir, { recursive: true, force: true });
  });

  await runMigrations();
  const userId = randomUUID();
  await db.insert(users).values({
    id: userId,
    name: "Service test user",
    email: `${userId}@example.test`,
  });

  const device = await createDevice(db, {
    userId,
    name: "Test PC",
    tokenHash: "token-hash-for-test",
    hostname: "test-host",
    os: "test-os",
    agentVersion: "0.1.0",
  });
  assert.equal((await findActiveByTokenHash(db, device.tokenHash))?.id, device.id);
  assert.equal(await revoke(db, userId, device.id), true);
  assert.equal(await findActiveByTokenHash(db, device.tokenHash), null);

  const pairing = newPairingCode();
  await createPairingCode(db, {
    userId,
    codeHash: pairing.hash,
    deviceName: "Paired PC",
    expiresAt: new Date(Date.now() + 60_000),
  });
  assert.deepEqual(await redeemPairingCode(db, hashPairingCode(pairing.plaintext)), {
    userId,
    deviceName: "Paired PC",
  });
  assert.equal(await redeemPairingCode(db, pairing.hash), null);

  const commandDevice = await createDevice(db, {
    userId,
    name: "Command PC",
    tokenHash: "command-token-hash-for-test",
  });
  const { commandId } = await enqueue(db, {
    userId,
    deviceId: commandDevice.id,
    type: "PAUSE",
  });
  assert.deepEqual(await takePending(db, commandDevice.id), [{ id: commandId, type: "PAUSE", arg: "" }]);
  await recordAck(db, { deviceId: commandDevice.id, commandId, ok: true, message: "done" });
  const acknowledged = await getCommand(db, userId, commandDevice.id, commandId);
  assert.equal(acknowledged?.status, "acked");
  assert.equal(acknowledged?.ok, true);

  // Lease behavior: a freshly delivered (but unacked) command is NOT redelivered within the lease
  // window, so a chatty long-poll does not resend the same command on every poll.
  const { commandId: leasedId } = await enqueue(db, {
    userId,
    deviceId: commandDevice.id,
    type: "RESUME",
  });
  assert.deepEqual(await takePending(db, commandDevice.id), [{ id: leasedId, type: "RESUME", arg: "" }]);
  assert.deepEqual(await takePending(db, commandDevice.id), []);
  // Once acked it stays out of the redelivery set.
  await recordAck(db, { deviceId: commandDevice.id, commandId: leasedId, ok: true });
  assert.deepEqual(await takePending(db, commandDevice.id), []);

  assert.equal(await appendLogs(db, {
    deviceId: commandDevice.id,
    userId,
    lines: [{ seq: 1, line: "first" }, { seq: 2, line: "second" }],
  }), 2);
  assert.equal(await appendLogs(db, {
    deviceId: commandDevice.id,
    userId,
    lines: [{ seq: 2, line: "duplicate" }],
  }), 0);
  const firstPage = await getLogsSince(db, { deviceId: commandDevice.id, limit: 1 });
  assert.equal(firstPage.lines.length, 1);
  assert.equal(firstPage.lines[0]?.line, "first");
  const secondPage = await getLogsSince(db, { deviceId: commandDevice.id, sinceId: firstPage.lastId, limit: 1 });
  assert.equal(secondPage.lines.length, 1);
  assert.equal(secondPage.lines[0]?.line, "second");

  // Revocation gate: a command enqueued while active is NOT claimed once the device is revoked.
  await enqueue(db, { userId, deviceId: commandDevice.id, type: "STOP" });
  assert.equal(await revoke(db, userId, commandDevice.id), true);
  assert.deepEqual(await takePending(db, commandDevice.id), []);
});

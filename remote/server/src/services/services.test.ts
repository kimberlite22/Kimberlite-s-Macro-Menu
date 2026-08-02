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
const { createDevice, findActiveByTokenHash, revoke } = await import("./devices.js");
const { enqueue, getCommand, recordAck, takePending } = await import("./commands.js");
const { appendLogs, getLogsSince } = await import("./logs.js");
const { upsertStatus, getStatus, listSessions } = await import("./status.js");
const { db, closeDb } = await import("../db/client.js");
const { runMigrations } = await import("../db/migrate.js");

test("device, command, log, and status services work against PGlite", async (t) => {
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

  // Status upsert + session archiving: a device_status row is a single always-overwritten
  // snapshot; a session boundary (sessionId change) archives the PREVIOUS snapshot into
  // device_sessions instead of just discarding it.
  const statusDevice = await createDevice(db, {
    userId,
    name: "Status PC",
    tokenHash: "status-token-hash-for-test",
  });
  await upsertStatus(db, {
    deviceId: statusDevice.id,
    userId,
    snapshot: { sessionId: "session-1", sessionTimeMs: 5000, currentScreen: "Start" },
    macroOnline: true,
  });
  assert.equal(await listSessions(db, statusDevice.id).then((rows) => rows.length), 0);

  // Same sessionId again (a routine ~1x/sec heartbeat) must NOT archive anything.
  await upsertStatus(db, {
    deviceId: statusDevice.id,
    userId,
    snapshot: { sessionId: "session-1", sessionTimeMs: 9000, currentScreen: "Battle" },
    macroOnline: true,
  });
  assert.equal(await listSessions(db, statusDevice.id).then((rows) => rows.length), 0);
  const midStatus = await getStatus(db, statusDevice.id);
  assert.equal((midStatus?.snapshotJson as Record<string, unknown> | undefined)?.currentScreen, "Battle");

  // A new sessionId (a restart) archives the LAST snapshot of the previous session.
  await upsertStatus(db, {
    deviceId: statusDevice.id,
    userId,
    snapshot: { sessionId: "session-2", sessionTimeMs: 0, currentScreen: "Start" },
    macroOnline: true,
  });
  const archived = await listSessions(db, statusDevice.id);
  assert.equal(archived.length, 1);
  assert.equal(archived[0]?.sessionId, "session-1");
  assert.equal((archived[0]?.snapshotJson as Record<string, unknown>).sessionTimeMs, 9000);
  const finalStatus = await getStatus(db, statusDevice.id);
  assert.equal((finalStatus?.snapshotJson as Record<string, unknown> | undefined)?.sessionId, "session-2");
});

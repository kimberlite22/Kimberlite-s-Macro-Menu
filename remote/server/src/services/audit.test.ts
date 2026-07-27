import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

// Select a throwaway DB before dynamically importing modules that evaluate env.ts.
const dataDir = await mkdtemp(join(tmpdir(), "anime-expedition-audit-test-"));
process.env.NODE_ENV = "test";
process.env.DATABASE_URL = "";
process.env.DATA_DIR = dataDir;

const { users } = await import("../db/schema.js");
const { db, closeDb } = await import("../db/client.js");
const { runMigrations } = await import("../db/migrate.js");
const { listAudit, writeAudit } = await import("./audit.js");

test("audit events are listed newest first and respect the limit", async (t) => {
  t.after(async () => {
    await closeDb();
    await rm(dataDir, { recursive: true, force: true });
  });

  await runMigrations();
  const userId = randomUUID();
  await db.insert(users).values({
    id: userId,
    name: "Audit test user",
    email: `${userId}@example.test`,
  });

  await writeAudit(db, { userId, action: "first", detail: "one" });
  await writeAudit(db, { userId, action: "second", detail: "two" });

  const events = await listAudit(db, userId);
  assert.equal(events.length, 2);
  assert.equal(events[0]?.action, "second");
  assert.equal(events[1]?.action, "first");

  const limited = await listAudit(db, userId, 1);
  assert.equal(limited.length, 1);
  assert.equal(limited[0]?.action, "second");
});

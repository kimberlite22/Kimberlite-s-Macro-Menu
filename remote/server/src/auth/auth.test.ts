import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

// Select a throwaway DB and a real secret BEFORE importing anything that reads env.ts.
const dataDir = await mkdtemp(join(tmpdir(), "anime-expedition-auth-test-"));
process.env.NODE_ENV = "test";
process.env.DATABASE_URL = "";
process.env.DATA_DIR = dataDir;
process.env.AUTH_SECRET = "integration-test-secret-do-not-use-in-prod-000000";
process.env.PUBLIC_URL = "http://localhost:8787";

const { eq } = await import("drizzle-orm");
const { users } = await import("../db/schema.js");
const { db, closeDb } = await import("../db/client.js");
const { runMigrations } = await import("../db/migrate.js");
const { auth } = await import("./auth.js");

test("better-auth email+password works against Drizzle/PGlite", async (t) => {
  t.after(async () => {
    await closeDb();
    await rm(dataDir, { recursive: true, force: true });
  });

  await runMigrations();

  const email = "pilot@example.test";
  const password = "correct horse battery";

  // Sign up.
  const signUp = await auth.api.signUpEmail({ body: { email, name: "Pilot", password } });
  assert.ok(signUp.user?.id, "sign-up returns a user id");
  assert.equal(signUp.user.email, email);

  // The user row is really in the DB.
  const rows = await db.select().from(users).where(eq(users.email, email));
  assert.equal(rows.length, 1);

  // Sign in and confirm a session cookie is issued.
  const signInResponse = await auth.api.signInEmail({ body: { email, password }, asResponse: true });
  assert.equal(signInResponse.status, 200);
  const setCookie = signInResponse.headers.get("set-cookie");
  assert.ok(setCookie && setCookie.length > 0, "sign-in sets a session cookie");

  // The issued cookie resolves back to the same user via getSession.
  const cookiePair = setCookie.split(";")[0] ?? "";
  const session = await auth.api.getSession({ headers: new Headers({ cookie: cookiePair }) });
  assert.equal(session?.user.email, email);

  // Wrong password is rejected.
  await assert.rejects(
    auth.api.signInEmail({ body: { email, password: "wrong wrong wrong" } }),
    "wrong password is rejected",
  );
});

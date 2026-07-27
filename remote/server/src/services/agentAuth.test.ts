import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

// Select a throwaway DB and a real secret BEFORE importing anything that reads env.ts (see
// auth.test.ts for why the ordering matters: env.ts is evaluated once, at import time).
const dataDir = await mkdtemp(join(tmpdir(), "anime-expedition-agentauth-test-"));
process.env.NODE_ENV = "test";
process.env.DATABASE_URL = "";
process.env.DATA_DIR = dataDir;
process.env.AUTH_SECRET = "integration-test-secret-do-not-use-in-prod-000000";
process.env.PUBLIC_URL = "http://localhost:8787";

const { eq } = await import("drizzle-orm");
const { sessions } = await import("../db/schema.js");
const { db, closeDb } = await import("../db/client.js");
const { runMigrations } = await import("../db/migrate.js");
const { auth } = await import("../auth/auth.js");
const { resolveAgentAccount } = await import("./agentAuth.js");

async function sessionCount(userId: string): Promise<number> {
  return (await db.select().from(sessions).where(eq(sessions.userId, userId))).length;
}

/** Mirrors a browser's cookie jar: keeps only name=value from every Set-Cookie on a Response. */
function cookieHeaderFrom(response: Response): string {
  return response.headers.getSetCookie().map((c) => c.split(";", 1)[0]).join("; ");
}

/**
 * RFC 4648 base32 decode, needed only because the `totpURI` returned by enableTwoFactor encodes the
 * raw secret as base32 for display in an authenticator app - auth.api.generateTOTP wants that raw
 * secret back, not its base32 form (see node_modules/@better-auth/utils/dist/otp.mjs: `.url()` base32-
 * encodes, but `.totp()`/`.verify()` use the secret string as-is).
 */
function base32Decode(input: string): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0;
  let value = 0;
  const bytes: number[] = [];
  for (const char of input.replace(/=+$/, "").toUpperCase()) {
    const index = alphabet.indexOf(char);
    if (index === -1) throw new Error(`Invalid base32 character: ${char}`);
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((value >> bits) & 0xff);
    }
  }
  return Buffer.from(bytes).toString("utf8");
}

test("resolveAgentAccount covers register, login, and the TOTP 2FA challenge", async (t) => {
  t.after(async () => {
    await closeDb();
    await rm(dataDir, { recursive: true, force: true });
  });
  await runMigrations();

  const email = "agent-pilot@example.test";
  const password = "correct horse battery staple";

  const registered = await resolveAgentAccount({ mode: "register", email, password });
  assert.equal(registered.ok, true);
  if (!registered.ok) throw new Error("unreachable");
  assert.equal(registered.email, email);
  // signUpEmail's autoSignIn creates a real session as a side effect; resolveAgentAccount only wants
  // the userId, so it must sign that session back out rather than leaving it in the database.
  assert.equal(await sessionCount(registered.userId), 0, "register leaves no session behind");

  const duplicate = await resolveAgentAccount({ mode: "register", email, password });
  assert.deepEqual(duplicate, { ok: false, error: "email_already_registered" });

  const loggedIn = await resolveAgentAccount({ mode: "login", email, password });
  assert.equal(loggedIn.ok, true);
  if (!loggedIn.ok) throw new Error("unreachable");
  assert.equal(loggedIn.userId, registered.userId);
  assert.equal(await sessionCount(loggedIn.userId), 0, "login leaves no session behind");

  const wrongPassword = await resolveAgentAccount({ mode: "login", email, password: "not the password" });
  assert.deepEqual(wrongPassword, { ok: false, error: "invalid_credentials" });

  // Enable 2FA the same way the dashboard does: enable, then verify one code to activate it.
  const signInResponse = await auth.api.signInEmail({ body: { email, password }, asResponse: true });
  const sessionCookie = cookieHeaderFrom(signInResponse);
  const enabled = await auth.api.enableTwoFactor({
    body: { password },
    headers: new Headers({ cookie: sessionCookie }),
  });
  const secretParam = /[?&]secret=([^&]+)/.exec(enabled.totpURI)?.[1];
  assert.ok(secretParam, "enable response includes a totp URI with a secret");
  const secret = base32Decode(decodeURIComponent(secretParam));
  const activation = await auth.api.generateTOTP({ body: { secret } });
  await auth.api.verifyTOTP({ body: { code: activation.code }, headers: new Headers({ cookie: sessionCookie }) });

  // A 2FA-enabled account now demands a TOTP code; a missing/wrong code is rejected distinctly.
  const needsTotp = await resolveAgentAccount({ mode: "login", email, password });
  assert.deepEqual(needsTotp, { ok: false, error: "totp_required" });

  const wrongTotp = await resolveAgentAccount({ mode: "login", email, password, totp: "000000" });
  assert.deepEqual(wrongTotp, { ok: false, error: "invalid_totp" });

  // The account already carries one lingering session from the raw activation call two lines above
  // (that call is test setup, not resolveAgentAccount, so it is not this module's job to revoke it);
  // what matters is that resolveAgentAccount's OWN verifyTOTP session does not add a net new one.
  const sessionsBeforeFinalLogin = await sessionCount(registered.userId);
  const loginCode = await auth.api.generateTOTP({ body: { secret } });
  const withTotp = await resolveAgentAccount({ mode: "login", email, password, totp: loginCode.code });
  assert.equal(withTotp.ok, true);
  if (!withTotp.ok) throw new Error("unreachable");
  assert.equal(withTotp.userId, registered.userId);
  assert.equal(
    await sessionCount(registered.userId),
    sessionsBeforeFinalLogin,
    "a 2FA login leaves no additional session behind",
  );
});

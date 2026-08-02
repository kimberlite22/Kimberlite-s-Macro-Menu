// better-auth configuration. Auth/crypto is deliberately delegated to a mature library rather than
// hand-rolled (see remote/PROTOCOL.md section 4 and the project's security rules). This module owns
// sessions and password hashing; the app never touches password hashes directly.
import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { twoFactor } from "better-auth/plugins";
import { db } from "../db/client.js";
import { schema } from "../db/schema.js";
import { env } from "../env.js";

export const auth = betterAuth({
  appName: "Macro Menu Remote",
  secret: env.AUTH_SECRET,
  baseURL: env.PUBLIC_URL,
  basePath: "/api/auth",
  // Same-origin frontend; keep the trusted origin list tight.
  trustedOrigins: [env.PUBLIC_URL],
  database: drizzleAdapter(db, {
    provider: "pg",
    // Our Drizzle exports are plural (users, sessions, ...) but better-auth's model names are
    // singular. Map them explicitly so the adapter resolves each model to the right table.
    schema: {
      user: schema.users,
      session: schema.sessions,
      account: schema.accounts,
      verification: schema.verifications,
      twoFactor: schema.twoFactors,
    },
  }),
  // Optional TOTP-based two-factor authentication (opt-in per user).
  plugins: [twoFactor({ issuer: "Macro Menu Remote" })],
  emailAndPassword: {
    enabled: true,
    // No email-verification step in the MVP, but require a non-trivial password.
    minPasswordLength: 10,
    autoSignIn: true,
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7, // 7 days
    updateAge: 60 * 60 * 24, // refresh the cookie at most once per day
  },
  // Brute-force protection on the auth endpoints (in addition to the app-wide @fastify/rate-limit).
  // Enabled in every environment; the credential + TOTP paths get tighter windows.
  rateLimit: {
    enabled: true,
    window: 60,
    max: 60,
    storage: "memory",
    customRules: {
      "/sign-in/email": { window: 60, max: 10 },
      "/sign-up/email": { window: 300, max: 10 },
      "/two-factor/verify-totp": { window: 60, max: 10 },
      "/two-factor/verify-backup-code": { window: 60, max: 10 },
    },
  },
  advanced: {
    // Secure cookies only make sense behind TLS; in dev over plain HTTP they would break login.
    useSecureCookies: env.NODE_ENV === "production",
    // Align better-auth's rate-limit IP source with Fastify's trustProxy: only read a forwarded-for
    // header when a trusted proxy actually sits in front. Otherwise fall back to the socket IP, so a
    // direct client cannot rotate X-Forwarded-For to evade the auth (sign-in/2FA) rate limits.
    ipAddress: {
      ipAddressHeaders: env.TRUST_PROXY ? ["x-forwarded-for"] : [],
    },
  },
});

export type Auth = typeof auth;

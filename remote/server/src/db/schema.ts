import { sql } from "drizzle-orm";
import {
  bigserial,
  bigint,
  boolean,
  check,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";
import type { CommandType } from "../shared/commands.js";

export type CommandStatus = "pending" | "delivered" | "acked" | "error" | "expired";

/** better-auth user model. The SQL table name must remain exactly `user`. */
export const users = pgTable("user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: boolean("email_verified").notNull().default(false),
  image: text("image"),
  // Added by the better-auth twoFactor plugin.
  twoFactorEnabled: boolean("two_factor_enabled").notNull().default(false),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { mode: "date" }).notNull().defaultNow(),
});

/** better-auth twoFactor model. The SQL table name must remain exactly `two_factor`. */
export const twoFactors = pgTable("two_factor", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  secret: text("secret").notNull(),
  backupCodes: text("backup_codes").notNull(),
  verified: boolean("verified").notNull().default(true),
  failedVerificationCount: integer("failed_verification_count").notNull().default(0),
  lockedUntil: timestamp("locked_until", { mode: "date" }),
});

/** better-auth session model. The SQL table name must remain exactly `session`. */
export const sessions = pgTable("session", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  token: text("token").notNull().unique(),
  expiresAt: timestamp("expires_at", { mode: "date" }).notNull(),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { mode: "date" }).notNull().defaultNow(),
});

/** better-auth account model. The SQL table name must remain exactly `account`. */
export const accounts = pgTable("account", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  accessTokenExpiresAt: timestamp("access_token_expires_at", { mode: "date" }),
  refreshTokenExpiresAt: timestamp("refresh_token_expires_at", { mode: "date" }),
  scope: text("scope"),
  idToken: text("id_token"),
  password: text("password"),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { mode: "date" }).notNull().defaultNow(),
});

/** better-auth verification model. The SQL table name must remain exactly `verification`. */
export const verifications = pgTable("verification", {
  id: text("id").primaryKey(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: timestamp("expires_at", { mode: "date" }).notNull(),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { mode: "date" }).notNull().defaultNow(),
});

export const devices = pgTable("devices", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  tokenHash: text("token_hash").notNull().unique(),
  hostname: text("hostname"),
  os: text("os"),
  agentVersion: text("agent_version"),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
  lastSeenAt: timestamp("last_seen_at", { mode: "date" }),
  revokedAt: timestamp("revoked_at", { mode: "date" }),
});

export const pairingCodes = pgTable("pairing_codes", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  codeHash: text("code_hash").notNull(),
  deviceName: text("device_name"),
  expiresAt: timestamp("expires_at", { mode: "date" }).notNull(),
  usedAt: timestamp("used_at", { mode: "date" }),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
}, (table) => [index("pairing_codes_code_hash_idx").on(table.codeHash)]);

export const deviceStatus = pgTable("device_status", {
  deviceId: text("device_id").primaryKey().references(() => devices.id, { onDelete: "cascade" }),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  snapshotJson: jsonb("snapshot_json").notNull(),
  macroOnline: boolean("macro_online").notNull().default(false),
  macroTimestamp: text("macro_timestamp"),
  receivedAt: timestamp("received_at", { mode: "date" }).notNull().defaultNow(),
});

export const logs = pgTable("logs", {
  // mode "number" (not "bigint"): row ids and the agent's per-device seq stay well under 2^53, and a
  // JS number serializes cleanly to JSON (a bigint would throw in Fastify's serializer).
  id: bigserial("id", { mode: "number" }).primaryKey(),
  deviceId: text("device_id").notNull().references(() => devices.id, { onDelete: "cascade" }),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  seq: bigint("seq", { mode: "number" }).notNull(),
  line: text("line").notNull(),
  receivedAt: timestamp("received_at", { mode: "date" }).notNull().defaultNow(),
}, (table) => [
  uniqueIndex("logs_device_seq_unique").on(table.deviceId, table.seq),
  index("logs_device_id_idx").on(table.deviceId, table.id),
]);

export const commands = pgTable("commands", {
  id: text("id").primaryKey(),
  deviceId: text("device_id").notNull().references(() => devices.id, { onDelete: "cascade" }),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  type: text("type").$type<CommandType>().notNull(),
  arg: text("arg").notNull().default(""),
  status: text("status").$type<CommandStatus>().notNull().default("pending"),
  ok: boolean("ok"),
  message: text("message"),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
  deliveredAt: timestamp("delivered_at", { mode: "date" }),
  ackedAt: timestamp("acked_at", { mode: "date" }),
}, (table) => [
  index("commands_device_status_idx").on(table.deviceId, table.status),
  check("commands_status_check", sql`${table.status} in ('pending', 'delivered', 'acked', 'error', 'expired')`),
]);

export const audit = pgTable("audit", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  userId: text("user_id").references(() => users.id, { onDelete: "cascade" }),
  deviceId: text("device_id").references(() => devices.id, { onDelete: "cascade" }),
  action: text("action").notNull(),
  detail: text("detail"),
  ip: text("ip"),
  createdAt: timestamp("created_at", { mode: "date" }).notNull().defaultNow(),
});

/** Complete schema supplied to Drizzle and, later, the better-auth adapter. */
export const schema = {
  users,
  sessions,
  accounts,
  verifications,
  twoFactors,
  devices,
  pairingCodes,
  deviceStatus,
  logs,
  commands,
  audit,
};

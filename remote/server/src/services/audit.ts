import { desc, eq } from "drizzle-orm";
import { audit } from "../db/schema.js";
import type { Database } from "../db/types.js";

export interface WriteAuditInput {
  readonly userId?: string;
  readonly deviceId?: string;
  readonly action: string;
  readonly detail?: string;
  readonly ip?: string;
}

/** Writes an audit event without allowing an audit failure to affect the caller. */
export async function writeAudit(database: Database, input: WriteAuditInput): Promise<void> {
  try {
    await database.insert(audit).values(input);
  } catch {
    // Do not include request data or database errors here because they can contain sensitive values.
    console.warn("Audit write failed.", { action: input.action });
  }
}

/** Lists one user's newest audit events with a bounded, predictable page size. */
export async function listAudit(database: Database, userId: string, limit?: number) {
  const requestedLimit = limit ?? 100;
  const pageSize = Number.isFinite(requestedLimit)
    ? Math.min(500, Math.max(1, Math.floor(requestedLimit)))
    : 100;

  return database
    .select({
      id: audit.id,
      action: audit.action,
      detail: audit.detail,
      deviceId: audit.deviceId,
      ip: audit.ip,
      createdAt: audit.createdAt,
    })
    .from(audit)
    .where(eq(audit.userId, userId))
    .orderBy(desc(audit.createdAt), desc(audit.id))
    .limit(pageSize);
}

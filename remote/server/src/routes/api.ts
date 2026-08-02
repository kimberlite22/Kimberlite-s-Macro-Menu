import type { FastifyInstance, FastifyRequest } from "fastify";
import { requireSession } from "../auth/guard.js";
import { db } from "../db/client.js";
import { COMMAND_META, COMMAND_TYPES } from "../shared/commands.js";
import { enqueue, getCommand, ValidationError } from "../services/commands.js";
import { getOwned, listByUser, revoke } from "../services/devices.js";
import { getLogsSince } from "../services/logs.js";
import { getStatus, listSessions } from "../services/status.js";
import { listAudit, writeAudit } from "../services/audit.js";

interface DeviceParams {
  id: string;
}

interface CommandParams extends DeviceParams {
  commandId: string;
}

interface LogsQuery {
  since?: number;
  limit?: number;
}

interface SessionsQuery {
  limit?: number;
}

interface CommandBody {
  type: string;
  arg?: string;
}

interface AuditQuery {
  limit?: number;
}

const emptyQuerySchema = {
  type: "object",
  additionalProperties: false,
  properties: {},
} as const;

const deviceParamsSchema = {
  type: "object",
  additionalProperties: false,
  required: ["id"],
  properties: { id: { type: "string", minLength: 1 } },
} as const;

const commandParamsSchema = {
  type: "object",
  additionalProperties: false,
  required: ["id", "commandId"],
  properties: {
    id: { type: "string", minLength: 1 },
    commandId: { type: "string", minLength: 1 },
  },
} as const;

const logsQuerySchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    since: { type: "number", minimum: 0 },
    limit: { type: "number", minimum: 1, maximum: 1000 },
  },
} as const;

const sessionsQuerySchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    limit: { type: "number", minimum: 1, maximum: 200 },
  },
} as const;

const commandBodySchema = {
  type: "object",
  additionalProperties: false,
  required: ["type"],
  properties: {
    type: { type: "string", minLength: 1 },
    arg: { type: "string" },
  },
} as const;

const auditQuerySchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    limit: { type: "number", minimum: 1, maximum: 500 },
  },
} as const;

function sessionUser(request: FastifyRequest): { id: string; email: string; twoFactorEnabled: boolean } {
  if (request.user === undefined) throw new Error("Session authentication was not established.");
  return request.user;
}

async function ensureOwned(userId: string, deviceId: string) {
  return getOwned(db, userId, deviceId);
}

function isFresh(date: Date | null, maximumAgeMs: number): boolean {
  return date !== null && Date.now() - date.getTime() <= maximumAgeMs;
}

/** Browser-facing, session-authenticated API endpoints. */
export default async function apiRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.get("/api/me", {
    preHandler: requireSession,
    schema: { querystring: emptyQuerySchema },
  }, async (request) => {
    const user = sessionUser(request);
    return { id: user.id, email: user.email, twoFactorEnabled: user.twoFactorEnabled };
  });

  fastify.get("/api/commands", {
    preHandler: requireSession,
    schema: { querystring: emptyQuerySchema },
  }, async () => ({ types: COMMAND_TYPES, meta: COMMAND_META }));

  fastify.get<{ Querystring: AuditQuery }>("/api/audit", {
    preHandler: requireSession,
    schema: { querystring: auditQuerySchema },
  }, async (request) => {
    const user = sessionUser(request);
    return listAudit(db, user.id, request.query.limit);
  });

  fastify.get("/api/devices", {
    preHandler: requireSession,
    schema: { querystring: emptyQuerySchema },
  }, async (request) => {
    const user = sessionUser(request);
    const devices = await listByUser(db, user.id);
    return Promise.all(devices.map(async (device) => {
      const status = await getStatus(db, device.id);
      return {
        id: device.id,
        name: device.name,
        agentOnline: isFresh(device.lastSeenAt, 30_000),
        macroOnline: status !== null && status.macroOnline && isFresh(status.receivedAt, 15_000),
        lastSeenAt: device.lastSeenAt,
        revokedAt: device.revokedAt,
      };
    }));
  });

  fastify.post<{ Params: DeviceParams }>("/api/devices/:id/revoke", {
    preHandler: requireSession,
    schema: { params: deviceParamsSchema, querystring: emptyQuerySchema },
  }, async (request, reply) => {
    const user = sessionUser(request);
    if (await ensureOwned(user.id, request.params.id) === null) {
      return reply.code(404).send({ error: "not_found" });
    }
    await revoke(db, user.id, request.params.id);
    await writeAudit(db, {
      userId: user.id,
      deviceId: request.params.id,
      action: "device.revoked",
      ip: request.ip,
    });
    return { ok: true };
  });

  fastify.get<{ Params: DeviceParams }>("/api/devices/:id/status", {
    preHandler: requireSession,
    schema: { params: deviceParamsSchema, querystring: emptyQuerySchema },
  }, async (request, reply) => {
    const user = sessionUser(request);
    if (await ensureOwned(user.id, request.params.id) === null) {
      return reply.code(404).send({ error: "not_found" });
    }
    const status = await getStatus(db, request.params.id);
    if (status === null) return null;
    const snapshot = status.snapshotJson as Record<string, unknown>;
    return { ...snapshot, macroOnline: status.macroOnline, receivedAt: status.receivedAt };
  });

  fastify.get<{ Params: DeviceParams; Querystring: SessionsQuery }>("/api/devices/:id/sessions", {
    preHandler: requireSession,
    schema: { params: deviceParamsSchema, querystring: sessionsQuerySchema },
  }, async (request, reply) => {
    const user = sessionUser(request);
    if (await ensureOwned(user.id, request.params.id) === null) {
      return reply.code(404).send({ error: "not_found" });
    }
    const rows = await listSessions(db, request.params.id, request.query.limit);
    return rows.map((row) => ({
      id: row.id,
      sessionId: row.sessionId,
      snapshot: row.snapshotJson,
      endedAt: row.endedAt,
      createdAt: row.createdAt,
    }));
  });

  fastify.get<{ Params: DeviceParams; Querystring: LogsQuery }>("/api/devices/:id/logs", {
    preHandler: requireSession,
    schema: { params: deviceParamsSchema, querystring: logsQuerySchema },
  }, async (request, reply) => {
    const user = sessionUser(request);
    if (await ensureOwned(user.id, request.params.id) === null) {
      return reply.code(404).send({ error: "not_found" });
    }
    const page = await getLogsSince(db, {
      deviceId: request.params.id,
      sinceId: request.query.since,
      limit: request.query.limit,
    });
    // The browser wire contract names the timestamp "at" (see PROTOCOL.md section 4).
    return {
      lines: page.lines.map((line) => ({ id: line.id, seq: line.seq, line: line.line, at: line.receivedAt })),
      lastId: page.lastId,
    };
  });

  fastify.post<{ Params: DeviceParams; Body: CommandBody }>("/api/devices/:id/commands", {
    preHandler: requireSession,
    schema: { params: deviceParamsSchema, querystring: emptyQuerySchema, body: commandBodySchema },
  }, async (request, reply) => {
    const user = sessionUser(request);
    const device = await ensureOwned(user.id, request.params.id);
    if (device === null) {
      return reply.code(404).send({ error: "not_found" });
    }
    // A revoked device can never authenticate again, so it would never fetch the command; reject
    // rather than queue an unreachable command.
    if (device.revokedAt !== null) {
      return reply.code(409).send({ error: "device_revoked" });
    }
    try {
      const result = await enqueue(db, {
        userId: user.id,
        deviceId: request.params.id,
        type: request.body.type,
        arg: request.body.arg,
      });
      await writeAudit(db, {
        userId: user.id,
        deviceId: request.params.id,
        action: "command.enqueued",
        detail: request.body.type + (request.body.arg ? ` ${request.body.arg}` : ""),
        ip: request.ip,
      });
      return reply.send(result);
    } catch (error: unknown) {
      if (error instanceof ValidationError) {
        return reply.code(400).send({ error: error.message });
      }
      throw error;
    }
  });

  fastify.get<{ Params: CommandParams }>("/api/devices/:id/commands/:commandId", {
    preHandler: requireSession,
    schema: { params: commandParamsSchema, querystring: emptyQuerySchema },
  }, async (request, reply) => {
    const user = sessionUser(request);
    if (await ensureOwned(user.id, request.params.id) === null) {
      return reply.code(404).send({ error: "not_found" });
    }
    const command = await getCommand(db, user.id, request.params.id, request.params.commandId);
    if (command === null) return reply.code(404).send({ error: "not_found" });
    return {
      id: command.id,
      type: command.type,
      arg: command.arg,
      status: command.status,
      ok: command.ok,
      message: command.message,
      createdAt: command.createdAt,
      deliveredAt: command.deliveredAt,
      ackedAt: command.ackedAt,
    };
  });
}

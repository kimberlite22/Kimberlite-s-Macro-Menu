import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { db } from "../db/client.js";
import { env } from "../env.js";
import { deviceNotifier } from "../lib/longpoll.js";
import { hashDeviceToken, hashPairingCode, newDeviceToken } from "../security/tokens.js";
import { recordAck, takePending } from "../services/commands.js";
import {
  findActiveByTokenHash,
  redeemPairingCodeAndCreateDevice,
  touchLastSeen,
} from "../services/devices.js";
import { appendLogs } from "../services/logs.js";
import { upsertStatus } from "../services/status.js";
import { writeAudit } from "../services/audit.js";

interface DeviceIdentity {
  readonly id: string;
  readonly userId: string;
}

declare module "fastify" {
  interface FastifyRequest {
    // Populated by requireDevice on agent-authenticated routes.
    device?: DeviceIdentity;
  }
}

interface PairBody {
  code: string;
  hostname?: string;
  agentVersion?: string;
  os?: string;
}

interface CommandsQuery {
  wait?: number;
}

interface ReportBody {
  status?: Record<string, unknown>;
  logs?: Array<{ seq: number; line: string }>;
  acks?: Array<{ commandId: string; ok: boolean; message?: string }>;
}

const emptyQuerySchema = {
  type: "object",
  additionalProperties: false,
  properties: {},
} as const;

const pairBodySchema = {
  type: "object",
  additionalProperties: false,
  required: ["code"],
  properties: {
    code: { type: "string", minLength: 1, maxLength: 128 },
    hostname: { type: "string", maxLength: 255 },
    agentVersion: { type: "string", maxLength: 128 },
    os: { type: "string", maxLength: 255 },
  },
} as const;

const commandsQuerySchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    wait: { type: "number", minimum: 0 },
  },
} as const;

const reportBodySchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    status: { type: "object", additionalProperties: true },
    logs: {
      type: "array",
      maxItems: 1000,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["seq", "line"],
        properties: {
          // Cap seq below 2^53 so it round-trips exactly as a JS number (the column uses number mode).
          seq: { type: "integer", minimum: 0, maximum: 9007199254740991 },
          line: { type: "string", maxLength: 8192 },
        },
      },
    },
    acks: {
      type: "array",
      maxItems: 200,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["commandId", "ok"],
        properties: {
          commandId: { type: "string", minLength: 1, maxLength: 64 },
          ok: { type: "boolean" },
          message: { type: "string", maxLength: 1000 },
        },
      },
    },
  },
} as const;

/** Rejects missing, unknown, and revoked device bearer tokens. */
async function requireDevice(request: FastifyRequest, reply: FastifyReply): Promise<void> {
  const authorization = request.headers.authorization;
  const match = typeof authorization === "string" ? /^Bearer (.+)$/.exec(authorization) : null;
  if (match?.[1] === undefined) {
    await reply.code(401).send({ error: "unauthorized" });
    return;
  }

  const device = await findActiveByTokenHash(db, hashDeviceToken(match[1]));
  if (device === null) {
    await reply.code(401).send({ error: "unauthorized" });
    return;
  }

  request.device = { id: device.id, userId: device.userId };
  // Heartbeat persistence must not delay an agent response or make authentication unavailable.
  void touchLastSeen(db, device.id).catch(() => undefined);
}

function requiredDevice(request: FastifyRequest): DeviceIdentity {
  if (request.device === undefined) throw new Error("Device authentication was not established.");
  return request.device;
}

/** Agent-facing protocol endpoints. */
export default async function agentRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.decorateRequest("device", undefined);

  fastify.post<{ Body: PairBody }>("/api/agent/pair", {
    schema: { querystring: emptyQuerySchema, body: pairBodySchema },
  }, async (request, reply) => {
    const token = newDeviceToken();
    const { hostname, agentVersion, os } = request.body;
    // Redeem the code and create the device atomically: if either fails, the code is NOT consumed.
    const device = await redeemPairingCodeAndCreateDevice(db, {
      codeHash: hashPairingCode(request.body.code),
      tokenHash: token.hash,
      hostname,
      agentVersion,
      os,
    });
    if (device === null) {
      return reply.code(410).send({ error: "invalid_or_expired_code" });
    }
    await writeAudit(db, {
      userId: device.userId,
      deviceId: device.id,
      action: "device.paired",
      detail: hostname,
      ip: request.ip,
    });
    return { deviceToken: token.plaintext, deviceId: device.id, deviceName: device.name };
  });

  fastify.get("/api/agent/version", {
    schema: { querystring: emptyQuerySchema },
  }, async () => ({
    latest: env.AGENT_LATEST_VERSION,
    minSupported: env.AGENT_MIN_VERSION,
  }));

  fastify.get<{ Querystring: CommandsQuery }>("/api/agent/commands", {
    preHandler: requireDevice,
    schema: { querystring: commandsQuerySchema },
  }, async (request, reply) => {
    const device = requiredDevice(request);
    const requestedWait = request.query.wait ?? env.COMMAND_LONGPOLL_DEFAULT_SECONDS;
    const waitSeconds = Math.min(
      env.COMMAND_LONGPOLL_MAX_SECONDS,
      Math.max(0, requestedWait),
    );

    if (waitSeconds === 0) return { commands: await takePending(db, device.id) };

    // Client disconnects during the wait surface as "close" on the RESPONSE socket (reply.raw), not
    // on the already-received request. Aborting frees the waiter immediately.
    const controller = new AbortController();
    const abort = (): void => controller.abort();
    reply.raw.once("close", abort);
    try {
      // Arm the waiter BEFORE the first takePending, so a command enqueued in the tiny window between
      // the check and the wait still wakes us (notify() would otherwise be lost). wait() registers
      // its resolver synchronously, so a notify() that fires before we await is not missed.
      const waiter = deviceNotifier.wait(device.id, waitSeconds * 1_000, controller.signal);
      let commands = await takePending(db, device.id);
      if (commands.length === 0) {
        await waiter;
        // takePending atomically refuses to claim commands for a device revoked during the wait, so
        // no separate (racy) re-check is needed here.
        commands = await takePending(db, device.id);
      }
      return { commands };
    } finally {
      controller.abort();
      reply.raw.removeListener("close", abort);
    }
  });

  fastify.post<{ Body: ReportBody }>("/api/agent/report", {
    preHandler: requireDevice,
    schema: { querystring: emptyQuerySchema, body: reportBodySchema },
  }, async (request) => {
    const device = requiredDevice(request);
    const { status, logs, acks } = request.body;

    if (status !== undefined) {
      await upsertStatus(db, {
        deviceId: device.id,
        userId: device.userId,
        snapshot: status,
        macroOnline: !!status.macroOnline,
        macroTimestamp: typeof status.timestamp === "string" ? status.timestamp : undefined,
      });
    }
    if (logs !== undefined) {
      await appendLogs(db, {
        deviceId: device.id,
        userId: device.userId,
        lines: logs.map((entry) => ({ seq: Number(entry.seq), line: String(entry.line) })),
      });
    }
    if (acks !== undefined) {
      for (const ack of acks) {
        await recordAck(db, {
          deviceId: device.id,
          commandId: ack.commandId,
          ok: !!ack.ok,
          message: ack.message,
        });
      }
    }

    return { ok: true, nextPollMs: 1_000, latestAgentVersion: env.AGENT_LATEST_VERSION };
  });
}

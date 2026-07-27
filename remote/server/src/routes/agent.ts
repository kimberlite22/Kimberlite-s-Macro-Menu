import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { db } from "../db/client.js";
import { env } from "../env.js";
import { deviceNotifier } from "../lib/longpoll.js";
import { hashDeviceToken, newDeviceToken } from "../security/tokens.js";
import { type AgentAuthError, resolveAgentAccount } from "../services/agentAuth.js";
import { recordAck, takePending } from "../services/commands.js";
import { createDevice, findActiveByTokenHash, touchLastSeen } from "../services/devices.js";
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

interface AgentAuthBody {
  mode: "login" | "register";
  email: string;
  password: string;
  totp?: string;
  deviceName?: string;
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

const agentAuthBodySchema = {
  type: "object",
  additionalProperties: false,
  required: ["mode", "email", "password"],
  properties: {
    mode: { type: "string", enum: ["login", "register"] },
    email: { type: "string", minLength: 1, maxLength: 255 },
    password: { type: "string", minLength: 1, maxLength: 512 },
    totp: { type: "string", maxLength: 32 },
    deviceName: { type: "string", minLength: 1, maxLength: 255 },
    hostname: { type: "string", maxLength: 255 },
    agentVersion: { type: "string", maxLength: 128 },
    os: { type: "string", maxLength: 255 },
  },
} as const;

/** Maps a resolveAgentAccount failure to the HTTP status the agent should see. */
function agentAuthErrorStatus(error: AgentAuthError): number {
  switch (error) {
    case "invalid_request":
      return 400;
    case "email_already_registered":
      return 409;
    // Matches better-auth's own status for this case (ACCOUNT_TEMPORARILY_LOCKED /
    // TOO_MANY_ATTEMPTS_REQUEST_NEW_CODE both throw as "TOO_MANY_REQUESTS") and keeps it clearly
    // distinct from a plain wrong password/code (401).
    case "account_locked":
      return 429;
    default:
      return 401;
  }
}

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

  // No requireDevice/requireSession guard: this is exactly how an unauthenticated caller identifies
  // itself here, by presenting the account's own email/password (+ optional TOTP). Rate-limited well
  // below the app-wide default (env.RATE_LIMIT_MAX) since it is a raw-credential endpoint - relying
  // solely on better-auth's own internal brute-force limiter would be riskier here, since that limiter
  // is designed around real HTTP requests (IP extraction from a live connection), not this in-process
  // auth.api.* call path.
  fastify.post<{ Body: AgentAuthBody }>("/api/agent/auth", {
    schema: { querystring: emptyQuerySchema, body: agentAuthBodySchema },
    config: { rateLimit: { max: 10, timeWindow: "1 minute" } },
  }, async (request, reply) => {
    const { mode, email, password, totp, deviceName, hostname, agentVersion, os } = request.body;
    const result = await resolveAgentAccount({ mode, email, password, totp });
    if (!result.ok) {
      return reply.code(agentAuthErrorStatus(result.error)).send({ error: result.error });
    }

    const token = newDeviceToken();
    const device = await createDevice(db, {
      userId: result.userId,
      name: deviceName || hostname || "device",
      tokenHash: token.hash,
      hostname,
      os,
      agentVersion,
    });
    await writeAudit(db, {
      userId: result.userId,
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

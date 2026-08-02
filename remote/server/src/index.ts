import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import cookie from "@fastify/cookie";
import rateLimit from "@fastify/rate-limit";
import fastifyStatic from "@fastify/static";
import Fastify from "fastify";
import { sql } from "drizzle-orm";
import { fromNodeHeaders } from "better-auth/node";
import { auth } from "./auth/auth.js";
import { closeDb, db, usingPostgres } from "./db/client.js";
import { runMigrations } from "./db/migrate.js";
import { env } from "./env.js";
import agentRoutes from "./routes/agent.js";
import apiRoutes from "./routes/api.js";
import { ValidationError } from "./services/commands.js";

const fastify = Fastify({
  bodyLimit: 1_048_576,
  trustProxy: env.TRUST_PROXY,
  logger: env.NODE_ENV === "production"
    ? true
    : { transport: { target: "pino-pretty" } },
});

function isRequestValidationError(error: unknown): error is { validation: unknown } {
  return typeof error === "object" && error !== null && "validation" in error && error.validation !== undefined;
}

function isRateLimitError(error: unknown): boolean {
  return typeof error === "object" && error !== null && "statusCode" in error && error.statusCode === 429;
}

fastify.register(cookie);
fastify.register(rateLimit, {
  global: true,
  max: env.RATE_LIMIT_MAX,
  timeWindow: env.RATE_LIMIT_WINDOW,
  // An agent reports about once per second and command long-polls count only when they complete;
  // 300 requests per minute therefore leaves ample headroom for normal agent and browser traffic.
  allowList: (request) => new URL(request.url, "http://localhost").pathname.startsWith("/health"),
  errorResponseBuilder: () => Object.assign(new Error("Too many requests."), { statusCode: 429 }),
});

// Force revalidation of the SPA assets so a redeployed index.html / app.js is never served stale
// from the browser cache. Applies to static files and the SPA fallback (all non-API GETs).
fastify.addHook("onSend", async (request, reply, payload) => {
  if (request.method === "GET" && !request.url.startsWith("/api")) {
    reply.header("Cache-Control", "no-cache");
  }
  return payload;
});

// Better Auth owns its complete route subtree and must run before the application API plugins.
fastify.route({
  method: ["GET", "POST"],
  url: "/api/auth/*",
  async handler(request, reply) {
    const url = new URL(request.url, `http://${request.headers.host}`);
    const headers = fromNodeHeaders(request.headers);
    const req = new Request(url.toString(), {
      method: request.method,
      headers,
      ...(request.body ? { body: JSON.stringify(request.body) } : {}),
    });
    const response = await auth.handler(req);
    reply.status(response.status);
    response.headers.forEach((value, key) => reply.header(key, value));
    return reply.send(response.body ? await response.text() : null);
  },
});

fastify.register(agentRoutes);
fastify.register(apiRoutes);

fastify.get("/health", {
  schema: {
    querystring: { type: "object", additionalProperties: false, properties: {} },
  },
}, async () => ({
  status: "ok",
  uptime: process.uptime(),
  db: usingPostgres ? "postgres" : "pglite",
}));

// Readiness probe: only 200 when a trivial DB query succeeds. Point uptime monitors / load balancers
// here (liveness at /health, readiness here).
fastify.get("/health/ready", {
  schema: { querystring: { type: "object", additionalProperties: false, properties: {} } },
}, async (_request, reply) => {
  try {
    await db.execute(sql`select 1`);
    return { status: "ready", db: usingPostgres ? "postgres" : "pglite" };
  } catch (error: unknown) {
    fastify.log.error(error, "Readiness check failed.");
    return reply.code(503).send({ status: "unavailable" });
  }
});

const webRoot = fileURLToPath(new URL("../web", import.meta.url));
const hasWebRoot = existsSync(webRoot);
if (hasWebRoot) {
  // no-cache: the browser must revalidate the SPA assets (ETag) each load, so an updated
  // index.html / app.js is never served stale from cache after a redeploy.
  fastify.register(fastifyStatic, { root: webRoot });
} else {
  fastify.log.warn({ webRoot }, "Frontend directory is absent; static serving is disabled.");
}

fastify.setNotFoundHandler((request, reply) => {
  if (hasWebRoot && request.method === "GET" && !request.url.startsWith("/api") && !request.url.startsWith("/health")) {
    return reply.sendFile("index.html");
  }
  return reply.code(404).send({ error: "not_found" });
});

fastify.setErrorHandler((error, _request, reply) => {
  if (isRateLimitError(error)) {
    return reply.code(429).send({ error: "too_many_requests" });
  }
  if (error instanceof ValidationError) {
    return reply.code(400).send({ error: error.message });
  }
  if (isRequestValidationError(error)) {
    return reply.code(400).send({ error: "invalid_request" });
  }
  fastify.log.error(error);
  return reply.code(500).send({ error: "internal_error" });
});

let shuttingDown = false;
async function shutdown(signal: string): Promise<void> {
  if (shuttingDown) return;
  shuttingDown = true;
  fastify.log.info({ signal }, "Shutting down.");
  try {
    await fastify.close();
    await closeDb();
  } catch (error: unknown) {
    fastify.log.error(error, "Error during shutdown.");
    process.exitCode = 1;
  }
}

async function boot(): Promise<void> {
  await runMigrations();
  const address = await fastify.listen({ host: env.HOST, port: env.PORT });
  fastify.log.info({ address }, "Macro Menu Remote server is listening.");

  process.once("SIGINT", () => { void shutdown("SIGINT"); });
  process.once("SIGTERM", () => { void shutdown("SIGTERM"); });
}

void boot().catch(async (error: unknown) => {
  fastify.log.error(error, "Server boot failed.");
  await fastify.close().catch(() => undefined);
  await closeDb().catch(() => undefined);
  process.exitCode = 1;
});

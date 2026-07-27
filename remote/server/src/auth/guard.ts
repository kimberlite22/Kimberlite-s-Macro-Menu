import type { FastifyReply, FastifyRequest } from "fastify";
import { fromNodeHeaders } from "better-auth/node";
import { auth } from "./auth.js";

export interface SessionUser {
  readonly id: string;
  readonly email: string;
  readonly twoFactorEnabled: boolean;
}

declare module "fastify" {
  interface FastifyRequest {
    // Populated by requireSession; present on every route guarded by it.
    user?: SessionUser;
  }
}

/**
 * Fastify preHandler that requires a valid better-auth session. On success it attaches request.user
 * (the authenticated tenant) and lets the route run; otherwise it replies 401 and short-circuits, so
 * a guarded handler can assume request.user is always defined.
 */
export async function requireSession(request: FastifyRequest, reply: FastifyReply) {
  const session = await auth.api.getSession({ headers: fromNodeHeaders(request.headers) });
  if (!session?.user) {
    return reply.code(401).send({ error: "unauthorized" });
  }
  request.user = {
    id: session.user.id,
    email: session.user.email,
    // The twoFactor plugin adds this field to the user; read it defensively so the base type suffices.
    twoFactorEnabled: Boolean((session.user as { twoFactorEnabled?: boolean }).twoFactorEnabled),
  };
}

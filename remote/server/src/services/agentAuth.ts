// Resolves an agent's login/register request directly against better-auth's server-side API
// (auth.api.*), entirely in-process - no browser, no cookie jar of its own. This is the security-
// relevant core of the account-based pairing flow described in PROTOCOL.md section 3.1: replacing
// the old one-time pair code with the account's own email/password (+ optional TOTP challenge).
//
// better-auth calls this "calling an endpoint directly" and it runs the SAME handler (including the
// two-factor plugin's hooks) that the HTTP route /api/auth/* would run. A 2FA-enabled account's
// sign-in does not return a session immediately; instead it sets a short-lived, signed "two factor"
// cookie and reports { twoFactorRedirect: true }. That cookie must be threaded into a follow-up
// verifyTOTP call for the challenge to complete - see cookieHeaderFrom below, which mimics a
// browser's cookie jar (store every Set-Cookie, replay every name=value pair) without hardcoding the
// plugin's internal cookie name (which varies with the configured prefix / secure-cookie mode).
import { APIError } from "better-auth";
import { auth } from "../auth/auth.js";

export type AgentAuthMode = "login" | "register";

export interface AgentAuthInput {
  readonly mode: AgentAuthMode;
  readonly email: string;
  readonly password: string;
  /** TOTP code for a 2FA-enabled account. Ignored for "register" (a brand new account has no 2FA yet). */
  readonly totp?: string;
}

export type AgentAuthError =
  | "invalid_request"
  | "invalid_credentials"
  | "totp_required"
  | "invalid_totp"
  | "email_already_registered"
  | "account_locked";

export type AgentAuthResult =
  | { readonly ok: true; readonly userId: string; readonly email: string }
  | { readonly ok: false; readonly error: AgentAuthError };

/**
 * Builds a `Cookie` header value from every `Set-Cookie` on a better-auth Response, keeping only the
 * name=value pair (dropping Path/HttpOnly/etc.) - equivalent to what a browser's cookie jar would
 * send back on the next request.
 */
function cookieHeaderFrom(response: Response): string {
  return response.headers
    .getSetCookie()
    .map((setCookie) => setCookie.split(";", 1)[0]?.trim())
    .filter((pair): pair is string => Boolean(pair))
    .join("; ");
}

function mapErrorCode(code: string | undefined): AgentAuthError {
  switch (code) {
    case "INVALID_EMAIL_OR_PASSWORD":
      return "invalid_credentials";
    case "USER_ALREADY_EXISTS":
    case "USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL":
      return "email_already_registered";
    case "INVALID_CODE":
    case "INVALID_TWO_FACTOR_COOKIE":
      return "invalid_totp";
    // Better-auth's own TOTP brute-force guard (remote/PROTOCOL.md section 3.1): too many wrong
    // codes locks the account for a cooldown, or the 2FA challenge's own attempt budget is spent.
    // Map both to the same "wait and retry" outcome rather than the generic invalid_request/400
    // fallback, which would read like a client bug instead of an expected lockout.
    case "ACCOUNT_TEMPORARILY_LOCKED":
    case "TOO_MANY_ATTEMPTS_REQUEST_NEW_CODE":
      return "account_locked";
    default:
      return "invalid_request";
  }
}

function mapAPIError(error: unknown): AgentAuthError {
  if (error instanceof APIError) {
    return mapErrorCode((error.body as { code?: string } | undefined)?.code);
  }
  return "invalid_request";
}

/**
 * better-call converts a thrown APIError into an ordinary (non-ok) Response instead of rethrowing
 * when the call is made with `asResponse: true` (see node_modules/better-call/dist/endpoint.mjs) -
 * so signInEmail's own bad-credential error never reaches a catch block here and must be read back
 * off the response body instead.
 */
async function errorFromResponse(response: Response): Promise<AgentAuthError> {
  const body = (await response.json().catch(() => undefined)) as { code?: string } | undefined;
  return mapErrorCode(body?.code);
}

/**
 * Every successful signInEmail/signUpEmail/verifyTOTP call creates a real, 7-day browser-style
 * session row (see auth.ts's `session.expiresIn`) as a side effect - this agent-auth flow only ever
 * wants the userId out of it, so that session would otherwise sit in the database unused for its
 * full lifetime. Sign it back out immediately; best-effort, since a cleanup failure here must never
 * turn an otherwise-successful pairing into a reported failure.
 */
async function revokeSession(response: Response): Promise<void> {
  const cookie = cookieHeaderFrom(response);
  if (cookie === "") return;
  try {
    await auth.api.signOut({ headers: new Headers({ cookie }) });
  } catch {
    // best-effort - the device is already paired at this point regardless of this cleanup.
  }
}

async function register(email: string, password: string): Promise<AgentAuthResult> {
  let signUpResponse: Response;
  try {
    signUpResponse = await auth.api.signUpEmail({ body: { email, name: email, password }, asResponse: true });
  } catch (error) {
    return { ok: false, error: mapAPIError(error) };
  }
  if (!signUpResponse.ok) {
    return { ok: false, error: await errorFromResponse(signUpResponse) };
  }

  const body = (await signUpResponse.json()) as { user?: { id: string; email: string } };
  await revokeSession(signUpResponse);
  if (body.user?.id === undefined) return { ok: false, error: "invalid_request" };
  return { ok: true, userId: body.user.id, email: body.user.email };
}

async function login(email: string, password: string, totp: string | undefined): Promise<AgentAuthResult> {
  const signInResponse = await auth.api.signInEmail({ body: { email, password }, asResponse: true });
  if (!signInResponse.ok) {
    return { ok: false, error: await errorFromResponse(signInResponse) };
  }

  const body = (await signInResponse.json()) as {
    twoFactorRedirect?: boolean;
    user?: { id: string; email: string };
  };

  if (body.twoFactorRedirect !== true) {
    await revokeSession(signInResponse);
    if (body.user?.id === undefined) return { ok: false, error: "invalid_request" };
    return { ok: true, userId: body.user.id, email: body.user.email };
  }

  if (totp === undefined || totp === "") return { ok: false, error: "totp_required" };

  let verifyResponse: Response;
  try {
    verifyResponse = await auth.api.verifyTOTP({
      body: { code: totp },
      headers: new Headers({ cookie: cookieHeaderFrom(signInResponse) }),
      asResponse: true,
    });
  } catch (error) {
    return { ok: false, error: mapAPIError(error) };
  }
  if (!verifyResponse.ok) {
    return { ok: false, error: await errorFromResponse(verifyResponse) };
  }

  const verified = (await verifyResponse.json()) as { user?: { id: string; email: string } };
  await revokeSession(verifyResponse);
  if (verified.user?.id === undefined) return { ok: false, error: "invalid_request" };
  return { ok: true, userId: verified.user.id, email: verified.user.email };
}

/** Resolves an agent's account credentials (login or register) to a userId, entirely server-side. */
export async function resolveAgentAccount(input: AgentAuthInput): Promise<AgentAuthResult> {
  if (input.email.trim() === "" || input.password === "") return { ok: false, error: "invalid_request" };
  return input.mode === "register"
    ? register(input.email, input.password)
    : login(input.email, input.password, input.totp);
}

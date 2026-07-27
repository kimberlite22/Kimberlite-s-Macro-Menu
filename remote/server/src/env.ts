/** Runtime configuration validated once when the server process starts. */
export type NodeEnvironment = "development" | "production" | "test";

export interface Environment {
  readonly PORT: number;
  readonly HOST: string;
  readonly NODE_ENV: NodeEnvironment;
  readonly PUBLIC_URL: string;
  readonly AUTH_SECRET: string;
  readonly DATABASE_URL?: string;
  readonly DATA_DIR: string;
  readonly COMMAND_LONGPOLL_DEFAULT_SECONDS: number;
  readonly COMMAND_LONGPOLL_MAX_SECONDS: number;
  readonly LOG_MAX_PER_DEVICE: number;
  readonly RATE_LIMIT_MAX: number;
  readonly RATE_LIMIT_WINDOW: string;
  readonly TRUST_PROXY: boolean;
  readonly AGENT_LATEST_VERSION: string;
  readonly AGENT_MIN_VERSION: string;
  /** How long a delivered-but-unacked command is left before it may be redelivered. */
  readonly COMMAND_LEASE_SECONDS: number;
  /** After this age an unacked command is expired (stop redelivering to an offline device). */
  readonly COMMAND_MAX_AGE_SECONDS: number;
}

const DEV_AUTH_SECRET = "development-only-auth-secret-change-before-production";

function optionalString(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed === "" || trimmed === undefined ? undefined : trimmed;
}

function numberSetting(name: string, fallback: number, minimum = 1): number {
  const raw = optionalString(process.env[name]);
  if (raw === undefined) return fallback;

  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < minimum) {
    throw new Error(`${name} must be an integer greater than or equal to ${minimum}.`);
  }
  return parsed;
}

function booleanSetting(name: string, fallback: boolean): boolean {
  const raw = optionalString(process.env[name]);
  if (raw === undefined) return fallback;
  if (raw === "true") return true;
  if (raw === "false") return false;
  throw new Error(`${name} must be true or false.`);
}

function nodeEnvironment(value: string | undefined): NodeEnvironment {
  const environment = optionalString(value) ?? "development";
  if (environment === "development" || environment === "production" || environment === "test") {
    return environment;
  }
  throw new Error("NODE_ENV must be development, production, or test.");
}

function createEnvironment(): Environment {
  // Load a local .env file if present (Node 20.12+). Absence is not an error: production is expected
  // to inject configuration through the real process environment instead of a committed file.
  try {
    process.loadEnvFile();
  } catch {
    // no .env file next to the working directory; fall back to the ambient environment
  }

  const NODE_ENV = nodeEnvironment(process.env.NODE_ENV);
  const PORT = numberSetting("PORT", 8787);
  // Secure by default: do NOT trust proxy headers unless explicitly enabled. Trusting
  // X-Forwarded-For without a real proxy in front lets clients spoof their IP and bypass the
  // IP-based rate limiter / falsify audit IPs. Set TRUST_PROXY=true ONLY when a trusted reverse
  // proxy (Caddy / Cloudflare Tunnel) terminates in front of the app (see the deployment docs).
  const TRUST_PROXY = booleanSetting("TRUST_PROXY", false);
  const configuredSecret = optionalString(process.env.AUTH_SECRET);
  let AUTH_SECRET = configuredSecret;

  if (AUTH_SECRET === undefined) {
    if (NODE_ENV === "production") {
      throw new Error("AUTH_SECRET is required when NODE_ENV is production.");
    }
    AUTH_SECRET = DEV_AUTH_SECRET;
    if (NODE_ENV === "development") {
      console.warn("AUTH_SECRET is not set; using the development-only authentication secret.");
    }
  } else if (NODE_ENV === "production" && AUTH_SECRET.length < 32) {
    // A short secret can be brute-forced offline from signed cookies and would compromise stored
    // TOTP secrets/backup codes if a DB backup leaks. Require real entropy (e.g. 32 random bytes).
    throw new Error("AUTH_SECRET must be at least 32 characters in production.");
  }

  const defaultLongPoll = numberSetting("COMMAND_LONGPOLL_DEFAULT_SECONDS", 25);
  const maximumLongPoll = numberSetting("COMMAND_LONGPOLL_MAX_SECONDS", 55);
  if (defaultLongPoll > maximumLongPoll) {
    throw new Error("COMMAND_LONGPOLL_DEFAULT_SECONDS cannot exceed COMMAND_LONGPOLL_MAX_SECONDS.");
  }

  const commandLease = numberSetting("COMMAND_LEASE_SECONDS", 30);
  const commandMaxAge = numberSetting("COMMAND_MAX_AGE_SECONDS", 300);
  if (commandLease > commandMaxAge) {
    throw new Error("COMMAND_LEASE_SECONDS cannot exceed COMMAND_MAX_AGE_SECONDS.");
  }

  return Object.freeze({
    PORT,
    HOST: optionalString(process.env.HOST) ?? "127.0.0.1",
    NODE_ENV,
    PUBLIC_URL: optionalString(process.env.PUBLIC_URL) ?? `http://localhost:${PORT}`,
    AUTH_SECRET,
    DATABASE_URL: optionalString(process.env.DATABASE_URL),
    DATA_DIR: optionalString(process.env.DATA_DIR) ?? "./.data",
    COMMAND_LONGPOLL_DEFAULT_SECONDS: defaultLongPoll,
    COMMAND_LONGPOLL_MAX_SECONDS: maximumLongPoll,
    LOG_MAX_PER_DEVICE: numberSetting("LOG_MAX_PER_DEVICE", 5000),
    RATE_LIMIT_MAX: numberSetting("RATE_LIMIT_MAX", 300),
    RATE_LIMIT_WINDOW: optionalString(process.env.RATE_LIMIT_WINDOW) ?? "1 minute",
    TRUST_PROXY,
    AGENT_LATEST_VERSION: optionalString(process.env.AGENT_LATEST_VERSION) ?? "0.1.0",
    AGENT_MIN_VERSION: optionalString(process.env.AGENT_MIN_VERSION) ?? "0.1.0",
    COMMAND_LEASE_SECONDS: commandLease,
    COMMAND_MAX_AGE_SECONDS: commandMaxAge,
  });
}

export const env: Environment = createEnvironment();

/** True when a PostgreSQL connection string selects the node-postgres driver. */
export function usePostgres(): boolean {
  return env.DATABASE_URL !== undefined;
}

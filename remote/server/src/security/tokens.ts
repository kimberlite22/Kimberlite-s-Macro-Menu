// Security-critical primitives for device tokens.
//
// Design notes (see remote/PROTOCOL.md section 5):
//   * A device token is 32 bytes of CSPRNG output (base64url). Because it is high-entropy, it is
//     stored ONLY as a SHA-256 hash and looked up by that hash; the plaintext is shown to the agent
//     exactly once (when a device is created) and never persisted server-side. A fast hash is
//     appropriate here precisely because the secret is high-entropy (unlike a human password, which
//     better-auth hashes with a slow KDF).
//   * Never log or return a token hash to a browser client. Never store plaintext.
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

/** Number of random bytes behind a device token. 32 bytes = 256 bits of entropy. */
const DEVICE_TOKEN_BYTES = 32;

function sha256Hex(input: string): string {
  return createHash("sha256").update(input, "utf8").digest("hex");
}

export interface GeneratedSecret {
  /** The plaintext to hand to the client exactly once. */
  readonly plaintext: string;
  /** The value to persist (a SHA-256 hex digest). */
  readonly hash: string;
}

/** Generates a new device token and its storage hash. */
export function newDeviceToken(): GeneratedSecret {
  const plaintext = randomBytes(DEVICE_TOKEN_BYTES).toString("base64url");
  return { plaintext, hash: sha256Hex(plaintext) };
}

/** Hashes a presented device token for lookup/comparison. */
export function hashDeviceToken(token: string): string {
  return sha256Hex(token);
}

/**
 * Constant-time comparison of two equal-length hex digests. Compares the raw characters rather than
 * the decoded bytes: Buffer.from(value, "hex") silently truncates at the first non-hex character, so
 * two different malformed inputs could otherwise decode to equal byte slices and compare "equal".
 * Returns false for any length mismatch or empty input rather than throwing.
 */
export function safeEqualHex(a: string, b: string): boolean {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length || a.length === 0) {
    return false;
  }
  const bufA = Buffer.from(a, "utf8");
  const bufB = Buffer.from(b, "utf8");
  return bufA.length === bufB.length && timingSafeEqual(bufA, bufB);
}

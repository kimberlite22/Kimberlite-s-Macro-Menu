// Security-critical primitives for device tokens and pairing codes.
//
// Design notes (see remote/PROTOCOL.md section 5):
//   * A device token is 32 bytes of CSPRNG output (base64url). Because it is high-entropy, it is
//     stored ONLY as a SHA-256 hash and looked up by that hash; the plaintext is shown to the agent
//     exactly once (at pairing) and never persisted server-side. A fast hash is appropriate here
//     precisely because the secret is high-entropy (unlike a human password, which better-auth hashes
//     with a slow KDF).
//   * A pairing code is short and human-pasteable, so it is deliberately LOW-ish entropy; it is made
//     safe by being single-use AND short-lived (see the TTL in the service layer), and it is also
//     stored only as a hash. It is normalized (upper-cased, separators stripped) before hashing so a
//     user can type it with or without the dash.
//   * Never log or return a token/code hash to a browser client. Never store plaintext.
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

/** Number of random bytes behind a device token. 32 bytes = 256 bits of entropy. */
const DEVICE_TOKEN_BYTES = 32;

/** Alphabet for human-pasteable pairing codes: no 0/O/1/I/L to avoid transcription errors. */
const PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
/** Number of characters in a pairing code (excluding the separator). 12 chars ~= 59 bits. */
const PAIRING_CODE_LEN = 12;

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
 * Normalizes a pairing code as typed by a human: trims, upper-cases, and removes any characters that
 * are not part of the alphabet (so dashes, spaces, etc. are ignored). Hashing is always done on the
 * normalized form, so display formatting never affects matching.
 */
export function normalizePairingCode(input: string): string {
  return input
    .toUpperCase()
    .split("")
    .filter((ch) => PAIRING_ALPHABET.includes(ch))
    .join("");
}

/**
 * Generates a new pairing code. `plaintext` is formatted with a dash for readability (e.g.
 * "ABCDE-FGHJK"); `hash` is the SHA-256 of the NORMALIZED code so it matches regardless of how the
 * user types it back.
 */
export function newPairingCode(): GeneratedSecret {
  const bytes = randomBytes(PAIRING_CODE_LEN);
  let raw = "";
  for (let i = 0; i < PAIRING_CODE_LEN; i++) {
    // Modulo bias is negligible here (31 into 256); acceptable for a short-lived, single-use code.
    raw += PAIRING_ALPHABET[bytes[i]! % PAIRING_ALPHABET.length];
  }
  const mid = Math.floor(PAIRING_CODE_LEN / 2);
  const plaintext = `${raw.slice(0, mid)}-${raw.slice(mid)}`;
  return { plaintext, hash: sha256Hex(raw) };
}

/** Hashes a pairing code (normalizing first) for lookup/comparison. */
export function hashPairingCode(code: string): string {
  return sha256Hex(normalizePairingCode(code));
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

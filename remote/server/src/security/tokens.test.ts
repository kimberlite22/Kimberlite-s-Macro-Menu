import assert from "node:assert/strict";
import test from "node:test";
import { hashDeviceToken, newDeviceToken, safeEqualHex } from "./tokens.js";

test("device tokens hash back to their stored hash", () => {
  const token = newDeviceToken();
  assert.equal(hashDeviceToken(token.plaintext), token.hash);
});

test("safeEqualHex handles equal, unequal, and differently sized values", () => {
  const first = "a".repeat(64);
  assert.equal(safeEqualHex(first, first), true);
  assert.equal(safeEqualHex(first, "b".repeat(64)), false);
  assert.equal(safeEqualHex(first, "a".repeat(62)), false);
});

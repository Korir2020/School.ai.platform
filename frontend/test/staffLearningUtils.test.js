import test from "node:test";
import assert from "node:assert/strict";
import {
  takedownReasonError,
  takedownPayload,
} from "../src/staffLearningUtils.js";

test("empty or blank reason is rejected", () => {
  assert.notEqual(takedownReasonError(""), "");
  assert.notEqual(takedownReasonError("   "), "");
  assert.notEqual(takedownReasonError(undefined), "");
});

test("reason of 500 characters is accepted, 501 is rejected", () => {
  assert.equal(takedownReasonError("a".repeat(500)), "");
  assert.notEqual(takedownReasonError("a".repeat(501)), "");
});

test("length is counted after trimming", () => {
  assert.equal(takedownReasonError("  " + "a".repeat(500) + "  "), "");
});

test("a normal reason is accepted and the payload is trimmed", () => {
  assert.equal(takedownReasonError("Licence withdrawn"), "");
  assert.deepEqual(takedownPayload("  Licence withdrawn "), {
    reason: "Licence withdrawn",
  });
});

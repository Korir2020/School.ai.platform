import test from "node:test";
import assert from "node:assert/strict";
import {
  buildLearningQuery,
  createLearningActivityPayload,
  isLearningExperienceRole,
  normalizeLearningLanguage,
} from "../src/learningExperienceUtils.js";

const deterministicCrypto = {
  getRandomValues(bytes) {
    bytes.fill(0);
    return bytes;
  },
};

test("only learner roles enter the independent learning experience shell", () => {
  assert.equal(isLearningExperienceRole("student"), true);
  assert.equal(isLearningExperienceRole("public_learner"), true);
  for (const role of ["teacher", "school_admin", "parent", "superadmin", "none", undefined]) {
    assert.equal(isLearningExperienceRole(role), false);
  }
});

test("learning query parameters are encoded, bounded, and omit empty filters", () => {
  const query = new URLSearchParams(buildLearningQuery({
    lang: "sw_KE", q: "  roots & shoots  ", topicId: 12, difficulty: "beginner", resourceType: "video",
  }));
  assert.equal(query.get("lang"), "sw-ke");
  assert.equal(query.get("q"), "roots & shoots");
  assert.equal(query.get("topic_id"), "12");
  assert.equal(query.get("difficulty"), "beginner");
  assert.equal(query.get("resource_type"), "video");
  assert.equal(query.has("framework"), false);
  assert.equal(normalizeLearningLanguage("fr-CA"), "fr-ca");
  assert.equal(normalizeLearningLanguage("bad code!"), "en");
});

test("resource activity payload uses a UUID, allowlisted target, and no client-supplied time", () => {
  const payload = createLearningActivityPayload({
    eventType: "started", targetField: "resource_id", targetId: "7",
  }, deterministicCrypto);
  assert.match(payload.idempotency_key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(payload.resource_id, 7);
  assert.deepEqual(payload.details, {});
  assert.equal("duration_seconds" in payload, false);
  assert.equal("occurred_at" in payload, false);
});

test("progress payload is limited to the API's self-reported checkpoints", () => {
  const payload = createLearningActivityPayload({
    eventType: "progress", targetField: "path_item_id", targetId: 19, checkpoint: "needs_help",
  }, deterministicCrypto);
  assert.equal(payload.path_item_id, 19);
  assert.deepEqual(payload.details, { checkpoint: "needs_help" });
  assert.throws(() => createLearningActivityPayload({
    eventType: "completed", targetField: "path_item_id", targetId: 19,
  }, deterministicCrypto), /supported self-reported/);
  assert.throws(() => createLearningActivityPayload({
    eventType: "progress", targetField: "resource_id", targetId: 19, checkpoint: "done",
  }, deterministicCrypto), /supported self-reported/);
});

test("activity creation fails closed without a secure random source", () => {
  assert.throws(() => createLearningActivityPayload({
    eventType: "started", targetField: "resource_id", targetId: 1,
  }, null), /Secure random IDs/);
});

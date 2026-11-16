import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeRecommendationPreferences,
  toggleRecommendationFormat,
  toggleRecommendationTopic,
} from "../src/learnerRecommendations.js";

const defaults = normalizeRecommendationPreferences(null);

test("recommendation preferences fail safe to empty, opted-in learning preferences", () => {
  assert.deepEqual(defaults, {
    topic_ids: [], preferred_formats: [], preferred_difficulty: "", recommendations_enabled: true,
  });
});

test("topic interest choices are positive unique IDs with a hard maximum of ten", () => {
  const loaded = normalizeRecommendationPreferences({
    topic_ids: [1, 2, 2, 0, -1, "3", ...Array.from({ length: 12 }, (_, index) => index + 4)],
  });
  assert.equal(loaded.topic_ids.length, 10);
  assert.deepEqual(loaded.topic_ids, [1, 2, 4, 5, 6, 7, 8, 9, 10, 11]);
  const unchangedAtLimit = toggleRecommendationTopic(loaded, 50);
  assert.deepEqual(unchangedAtLimit.topic_ids, loaded.topic_ids);
  const removed = toggleRecommendationTopic(loaded, 1);
  assert.equal(removed.topic_ids.includes(1), false);
  assert.equal(toggleRecommendationTopic(removed, 0), removed);
});

test("format and difficulty preferences accept only supported catalogue values", () => {
  const loaded = normalizeRecommendationPreferences({
    preferred_formats: ["video", "unknown", "video", "audio"],
    preferred_difficulty: "expert",
    recommendations_enabled: false,
  });
  assert.deepEqual(loaded.preferred_formats, ["video", "audio"]);
  assert.equal(loaded.preferred_difficulty, "");
  assert.equal(loaded.recommendations_enabled, false);
  const toggled = toggleRecommendationFormat(loaded, "worksheet");
  assert.deepEqual(toggled.preferred_formats, ["video", "audio", "worksheet"]);
  assert.deepEqual(toggleRecommendationFormat(toggled, "bad-format"), toggled);
});

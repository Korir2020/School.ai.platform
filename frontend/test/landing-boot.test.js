import test from "node:test";
import assert from "node:assert/strict";
import { bootDelay, BOOT_FADE_MS, BOOT_MAX_MS } from "../src/landing-boot.js";

test("the opening logo adds no more than half a second including its fade", () => {
  assert.equal(BOOT_MAX_MS, 500);
  assert.equal(bootDelay(0) + BOOT_FADE_MS, 500);
  assert.equal(bootDelay(200) + 200 + BOOT_FADE_MS, 500);
});
test("an already loaded or reduced-motion page has no extra opening hold", () => {
  assert.equal(bootDelay(900), 0);
  assert.equal(bootDelay(0, true), 0);
});
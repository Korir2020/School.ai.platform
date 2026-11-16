import test from "node:test";
import assert from "node:assert/strict";
import { agePolicyLines, isIndependentRegistrationAvailable } from "../src/independentLearningPolicy.js";

const completeMinorCapabilities = {
  independent_registration: true,
  age_verification: true,
  email_verification: true,
  sms_verification: true,
  guardian_identity_verification: true,
  guardian_consent_capture: true,
};

test("approved age policy preserves the 10 and 18 boundaries", () => {
  const lines = agePolicyLines(10);
  assert.deepEqual(lines.map((line) => line.range), ["Under 10", "10–17", "18 and above", "Unknown age"]);
});

test("configuration cannot lower the approved independent minimum", () => {
  assert.equal(agePolicyLines(9)[0].range, "Under 10");
  assert.equal(agePolicyLines(12)[0].range, "Under 12");
});

test("independent registration requires provider readiness and every minor safeguard", () => {
  assert.equal(isIndependentRegistrationAvailable({
    provider_ready: true,
    capabilities: { ...completeMinorCapabilities },
  }), true);
  assert.equal(isIndependentRegistrationAvailable({
    provider_ready: true,
    capabilities: { ...completeMinorCapabilities, guardian_identity_verification: false },
  }), false);
  assert.equal(isIndependentRegistrationAvailable({
    provider_ready: true,
    capabilities: { ...completeMinorCapabilities, sms_verification: false },
  }), false);
  assert.equal(isIndependentRegistrationAvailable({
    provider_ready: true,
    capabilities: { ...completeMinorCapabilities, guardian_consent_capture: false },
  }), false);
  assert.equal(isIndependentRegistrationAvailable({
    provider_ready: false,
    capabilities: { ...completeMinorCapabilities },
  }), false);
});

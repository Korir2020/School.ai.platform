export function agePolicyLines(minimumAge = 10) {
  const minimum = Number.isInteger(Number(minimumAge)) && Number(minimumAge) >= 10 && Number(minimumAge) < 18
    ? Number(minimumAge)
    : 10;
  return [
    { range: `Under ${minimum}`, rule: "School-managed account only; no independent public registration." },
    { range: `${minimum}–17`, rule: "Verified guardian involvement and consent are required." },
    { range: "18 and above", rule: "Independent self-registration is permitted after real age and contact verification." },
    { range: "Unknown age", rule: "Protected learning features stay blocked until age is established and verified." },
  ];
}

export function isIndependentRegistrationAvailable(capabilities) {
  return Boolean(
    capabilities?.provider_ready
    && capabilities?.capabilities?.independent_registration
    && capabilities?.capabilities?.age_verification
    && capabilities?.capabilities?.email_verification
    && capabilities?.capabilities?.sms_verification
    && capabilities?.capabilities?.guardian_identity_verification
    && capabilities?.capabilities?.guardian_consent_capture
  );
}

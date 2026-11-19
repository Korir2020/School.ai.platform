export const TAKEDOWN_REASON_MAX = 500;

export function takedownReasonError(text) {
  const reason = String(text ?? "").trim();
  if (!reason) return "Give a reason for the takedown.";
  if (reason.length > TAKEDOWN_REASON_MAX) {
    return `The reason must be ${TAKEDOWN_REASON_MAX} characters or fewer.`;
  }
  return "";
}

export function takedownPayload(text) {
  return { reason: String(text ?? "").trim() };
}

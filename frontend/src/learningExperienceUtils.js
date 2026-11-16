export const LEARNING_VIEWS = [
  { id: "home", label: "Home" },
  { id: "discover", label: "Discover" },
  { id: "recommendations", label: "Recommended" },
  { id: "paths", label: "Learning paths" },
  { id: "continue", label: "Continue" },
  { id: "goals", label: "Goals" },
  { id: "saved", label: "Saved" },
  { id: "account", label: "Account" },
];

export const LEARNING_CHECKPOINTS = [
  { value: "attempted", label: "I tried it" },
  { value: "reviewed", label: "I reviewed it" },
  { value: "needs_help", label: "I need help" },
  { value: "understood", label: "I understand this" },
];

export function isLearningExperienceRole(role) {
  return role === "student" || role === "public_learner";
}

export function normalizeLearningLanguage(value) {
  const language = String(value || "en").trim().replaceAll("_", "-").toLowerCase();
  return /^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/.test(language) ? language : "en";
}

export function buildLearningQuery({
  lang = "en", q = "", topicId = "", framework = "", difficulty = "", resourceType = "",
} = {}) {
  const params = new URLSearchParams();
  params.set("lang", normalizeLearningLanguage(lang));
  const normalizedQuery = String(q || "").trim();
  if (normalizedQuery) params.set("q", normalizedQuery.slice(0, 100));
  if (topicId) params.set("topic_id", String(topicId));
  if (framework) params.set("framework", String(framework));
  if (difficulty) params.set("difficulty", String(difficulty));
  if (resourceType) params.set("resource_type", String(resourceType));
  return `?${params.toString()}`;
}

function createUuid(cryptoSource) {
  if (typeof cryptoSource?.randomUUID === "function") return cryptoSource.randomUUID();
  if (typeof cryptoSource?.getRandomValues !== "function") {
    throw new Error("Secure random IDs are unavailable in this browser.");
  }
  const bytes = cryptoSource.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function createLearningActivityPayload({
  eventType, targetField, targetId, checkpoint, rating,
}, cryptoSource = globalThis.crypto) {
  if (!new Set(["resource_id", "path_item_id"]).has(targetField)) {
    throw new Error("Choose a supported learning activity target.");
  }
  if (!Number.isSafeInteger(Number(targetId)) || Number(targetId) <= 0) {
    throw new Error("The learning activity target is invalid.");
  }
  const payload = {
    idempotency_key: createUuid(cryptoSource),
    event_type: eventType,
    [targetField]: Number(targetId),
    details: {},
  };
  if (eventType === "started") return payload;
  if (eventType === "progress" && LEARNING_CHECKPOINTS.some((item) => item.value === checkpoint)) {
    payload.details = { checkpoint };
    return payload;
  }
  if (eventType === "feedback" && Number.isInteger(rating) && rating >= 1 && rating <= 5) {
    payload.details = { rating };
    return payload;
  }
  throw new Error("Choose a supported self-reported learning check-in.");
}

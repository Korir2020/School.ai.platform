function makeUuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  if (!globalThis.crypto?.getRandomValues) throw new Error("Secure operation IDs are unavailable in this browser.");
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function createDraftOperation({ exam, subject, entries }) {
  const offlineOperationId = makeUuid();
  return {
    offline_operation_id: offlineOperationId,
    body: { exam, subject, entries: entries.map((entry) => ({ ...entry })), offline_operation_id: offlineOperationId },
    status: "pending",
    created_at: new Date().toISOString(),
    attempts: 0,
  };
}

export function retryOperation(operations, operationId) {
  return operations.map((operation) => operation.offline_operation_id === operationId
    && ["failed", "conflict", "waiting"].includes(operation.status)
    ? { ...operation, status: "pending", last_error: "" } : operation);
}

const retryDelay = (attempts) => Math.min(60_000, 1_000 * (2 ** Math.min(6, Math.max(0, attempts - 1))));

export async function replayOperations(operations, send, now = Date.now()) {
  const next = [];
  for (const operation of operations) {
    if (!(["pending", "waiting"].includes(operation.status))) {
      next.push(operation);
      continue;
    }
    if (operation.status === "waiting" && Number(operation.retry_after || 0) > now) {
      next.push(operation);
      continue;
    }
    try {
      const response = await send(operation.body);
      if (response.ok) {
        next.push({ ...operation, status: "synced", attempts: operation.attempts + 1,
          synced_at: new Date().toISOString(), last_error: "", retry_after: null });
      } else {
        const conflict = response.status === 409 || response.status === 412;
        const attempts = operation.attempts + 1;
        const temporary = response.status === 429 || response.status >= 500;
        next.push({ ...operation, status: conflict ? "conflict" : temporary ? "waiting" : "failed", attempts,
          retry_after: temporary ? now + retryDelay(attempts) : null,
          last_error: `Draft batch was not saved (HTTP ${response.status}).` });
      }
    } catch {
      const attempts = operation.attempts + 1;
      next.push({ ...operation, status: "waiting", attempts, retry_after: now + retryDelay(attempts),
        last_error: "Waiting for a connection; this exact batch will be retried." });
    }
  }
  return next;
}

import test from "node:test";
import assert from "node:assert/strict";
import { decryptOfflinePayload, encryptOfflinePayload, PBKDF2_ITERATIONS } from "../src/offline/offlineCrypto.js";
import { isShellCacheRequest } from "../src/offline/cachePolicy.js";
import { createDraftOperation, replayOperations, retryOperation } from "../src/offline/operationQueue.js";

const ORIGIN = "https://school.example";
const SHELL_ASSETS = ["/assets/app.123.js", "/assets/main.123.css", "/assets/inter.woff2"];

test("offline payload encryption uses the required PBKDF2 floor and AES-GCM authentication", async () => {
  assert.ok(PBKDF2_ITERATIONS >= 310_000);
  const metadata = { username: "teacher.one", schoolId: "school-17", savedAt: 1_800_000_000_000, passphrase: "a long offline phrase" };
  const original = { marks: [{ student: "s-1", score: 12 }], private: true };
  const encrypted = await encryptOfflinePayload(original, metadata);
  assert.equal(typeof encrypted.ciphertext, "object");
  assert.deepEqual(await decryptOfflinePayload(encrypted, metadata, metadata.passphrase), original);
  await assert.rejects(() => decryptOfflinePayload(encrypted, metadata, "wrong passphrase"), /incorrect|changed/i);
  const altered = { ...encrypted, ciphertext: [...encrypted.ciphertext] };
  altered.ciphertext[0] ^= 1;
  await assert.rejects(() => decryptOfflinePayload(altered, metadata, metadata.passphrase), /incorrect|changed/i);
});

test("cache policy admits only known same-origin static shell GETs", () => {
  const request = (path, overrides = {}) => isShellCacheRequest({ url: `${ORIGIN}${path}`, origin: ORIGIN, ...overrides }, SHELL_ASSETS);
  assert.equal(request("/"), true);
  assert.equal(request("/index.html"), true);
  assert.equal(request("/assets/app.123.js"), true);
  assert.equal(request("/assets/inter.woff2"), true);
  assert.equal(request("/assets/unknown.js"), false);
  assert.equal(request("/assets/app.123.js?v=2"), false);
  assert.equal(request("/api/auth/me/"), false);
  assert.equal(request("/api/performance/batch/"), false);
  assert.equal(request("/reports/term/"), false);
  assert.equal(request("/receipts/123/"), false);
  assert.equal(request("/attachments/123/"), false);
  assert.equal(request("/assets/app.123.js", { method: "POST" }), false);
  assert.equal(isShellCacheRequest({ url: "https://other.example/assets/app.123.js", origin: ORIGIN }, SHELL_ASSETS), false);
  assert.equal(request("/assets/app.123.js", { authorization: true }), false);
});

test("draft queue replays the exact operation body and retains conflicts until explicit retry", async () => {
  const operation = createDraftOperation({ exam: 8, subject: 4, entries: [
    { student: 91, paper_number: 1, marks: 12.5, mark_status: "scored", expected_updated_at: "2026-10-01T10:00:00Z" },
    { student: 92, paper_number: 1, marks: null, mark_status: "absent", expected_updated_at: null },
  ] });
  assert.match(operation.offline_operation_id, /^[0-9a-f-]{36}$/i);
  assert.equal(operation.body.offline_operation_id, operation.offline_operation_id);
  const originalBody = structuredClone(operation.body);
  const sent = [];
  const conflict = await replayOperations([operation], async (body) => {
    sent.push(body);
    return { ok: false, status: 409 };
  });
  assert.deepEqual(sent[0], originalBody);
  assert.equal(conflict[0].status, "conflict");
  assert.equal(conflict[0].offline_operation_id, operation.offline_operation_id);
  assert.deepEqual(conflict[0].body, originalBody);
  assert.equal(conflict[0].attempts, 1);

  const retried = retryOperation(conflict, operation.offline_operation_id);
  assert.equal(retried[0].status, "pending");
  const sentAgain = [];
  const synced = await replayOperations(retried, async (body) => {
    sentAgain.push(body);
    return { ok: true, status: 200 };
  });
  assert.deepEqual(sentAgain[0], originalBody);
  assert.deepEqual(synced[0].body, originalBody);
  assert.equal(synced[0].status, "synced");
});

test("network interruption retains the same operation in a reconnect-retryable state", async () => {
  const operation = createDraftOperation({ exam: 1, subject: 2, entries: [
    { student: 3, paper_number: 2, marks: 0, mark_status: "scored", expected_updated_at: null },
  ] });
  const before = structuredClone(operation.body);
  const waiting = await replayOperations([operation], async () => { throw new TypeError("offline"); }, 1_000);
  assert.equal(waiting[0].status, "waiting");
  assert.equal(waiting[0].retry_after, 2_000);
  assert.deepEqual(waiting[0].body, before);
  const done = await replayOperations(waiting, async (body) => {
    assert.deepEqual(body, before);
    return { ok: true, status: 200 };
  }, waiting[0].retry_after);
  assert.equal(done[0].status, "synced");
  assert.deepEqual(done[0].body, before);
});

test("temporary server failures use bounded exponential backoff without overwriting the queued batch", async () => {
  const operation = createDraftOperation({ exam: 1, subject: 2, entries: [
    { student: 3, paper_number: 1, marks: 8, mark_status: "scored", expected_updated_at: null },
  ] });
  const before = structuredClone(operation.body);
  const first = await replayOperations([operation], async () => ({ ok: false, status: 503 }), 10_000);
  assert.equal(first[0].status, "waiting");
  assert.equal(first[0].retry_after, 11_000);
  assert.deepEqual(first[0].body, before);
  const skipped = await replayOperations(first, async () => { throw new Error("must not run early"); }, 10_500);
  assert.deepEqual(skipped, first);
  const second = await replayOperations(first, async () => ({ ok: false, status: 503 }), first[0].retry_after);
  assert.equal(second[0].retry_after, 13_000);
  assert.deepEqual(second[0].body, before);
});

import { decryptOfflinePayload, encryptOfflinePayload } from "./offlineCrypto";

export const OFFLINE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const DB_NAME = "marian-offline-v1";
const STORE = "encrypted-records";
const RECORD_ID = "teacher-marks";

function openDb() {
  if (!globalThis.indexedDB) return Promise.reject(new Error("This browser does not support private offline storage."));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open offline storage."));
  });
}

async function getRecord() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(STORE, "readonly").objectStore(STORE).get(RECORD_ID);
    request.onsuccess = () => { db.close(); resolve(request.result || null); };
    request.onerror = () => { db.close(); reject(request.error); };
  });
}

async function putRecord(record) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(record);
    tx.oncomplete = () => { db.close(); resolve(); };
    tx.onerror = () => { db.close(); reject(tx.error || new Error("Could not save encrypted offline data.")); };
    tx.onabort = () => { db.close(); reject(tx.error || new Error("Could not save encrypted offline data.")); };
  });
}

export async function clearOfflineData() {
  if (!globalThis.indexedDB) return;
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(RECORD_ID);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  }).finally(() => db.close());
}

async function storageStatus(requiredBytes = 0) {
  const storage = globalThis.navigator?.storage;
  if (!storage) return { persistent: false, quota: null, usage: null };
  let estimate = null;
  try { estimate = await storage.estimate?.(); } catch { /* Browser does not expose estimates. */ }
  const quota = Number.isFinite(estimate?.quota) ? estimate.quota : null;
  const usage = Number.isFinite(estimate?.usage) ? estimate.usage : null;
  if (quota !== null && usage !== null && quota - usage < requiredBytes + 1024 * 1024) {
    throw new Error("This device may not have enough browser storage for the prepared marks copy. Free space and try again.");
  }
  let persistent = false;
  try {
    persistent = typeof storage.persisted === "function" ? await storage.persisted() : false;
    if (!persistent && typeof storage.persist === "function") persistent = await storage.persist();
  } catch { /* The browser can deny persistent storage; report it without breaking use. */ }
  return { persistent: persistent === true, quota, usage };
}

export async function getOfflineMetadata() {
  const record = await getRecord();
  if (!record) return null;
  const metadata = { username: record.username, schoolId: record.schoolId,
    savedAt: record.savedAt, expiresAt: record.expiresAt,
    storagePersistent: record.storagePersistent === true,
    quota: Number.isFinite(record.quota) ? record.quota : null,
    usage: Number.isFinite(record.usage) ? record.usage : null };
  if (Date.now() >= record.expiresAt || record.expiresAt - record.savedAt > OFFLINE_MAX_AGE_MS) {
    await clearOfflineData();
    return { ...metadata, expired: true };
  }
  return metadata;
}

function checkIdentity(record, username, schoolId) {
  if (username && record.username.toLowerCase() !== String(username).trim().toLowerCase()) {
    throw new Error("This encrypted copy belongs to a different username.");
  }
  if (schoolId && String(record.schoolId) !== String(schoolId)) {
    throw new Error("This encrypted copy belongs to a different school.");
  }
}

export async function saveOfflinePayload(payload, passphrase) {
  const identity = payload?.identity;
  if (!identity?.username || !identity?.schoolId) throw new Error("A teacher username and school are required to prepare offline marks.");
  const savedAt = Date.now();
  const expiresAt = savedAt + OFFLINE_MAX_AGE_MS;
  const metadata = { username: String(identity.username).trim(), schoolId: String(identity.schoolId), savedAt, expiresAt, passphrase };
  const encryptedPayload = { ...payload, offlineMetadata: { savedAt, expiresAt } };
  const requiredBytes = new TextEncoder().encode(JSON.stringify(encryptedPayload)).byteLength;
  const storage = await storageStatus(requiredBytes);
  const encrypted = await encryptOfflinePayload(encryptedPayload, metadata);
  await putRecord({ id: RECORD_ID, username: metadata.username, schoolId: metadata.schoolId,
    savedAt, expiresAt, storagePersistent: storage.persistent, quota: storage.quota,
    usage: storage.usage, ...encrypted });
  return { username: metadata.username, schoolId: metadata.schoolId, savedAt, expiresAt, ...storage };
}

export async function loadOfflinePayload(passphrase, username, schoolId) {
  const record = await getRecord();
  if (!record) throw new Error("No prepared offline marks copy is available on this device.");
  if (Date.now() >= record.expiresAt || record.expiresAt - record.savedAt > OFFLINE_MAX_AGE_MS) {
    await clearOfflineData();
    throw new Error("This offline marks copy expired after seven days. Connect and prepare it again.");
  }
  checkIdentity(record, username, schoolId);
  const payload = await decryptOfflinePayload(record, record, passphrase);
  if (!payload?.identity || String(payload.identity.schoolId) !== String(record.schoolId)
    || payload.identity.username.toLowerCase() !== record.username.toLowerCase()
    || payload.identity.role !== "teacher") {
    throw new Error("The encrypted offline copy does not match its saved account and school.");
  }
  return payload;
}

export async function updateOfflinePayload(passphrase, update, username, schoolId) {
  const record = await getRecord();
  if (!record) throw new Error("No prepared offline marks copy is available on this device.");
  if (Date.now() >= record.expiresAt || record.expiresAt - record.savedAt > OFFLINE_MAX_AGE_MS) {
    await clearOfflineData();
    throw new Error("This offline marks copy expired after seven days. Connect and prepare it again.");
  }
  checkIdentity(record, username, schoolId);
  const current = await decryptOfflinePayload(record, record, passphrase);
  const next = await update(current);
  const encrypted = await encryptOfflinePayload(next, { ...record, passphrase }, new Uint8Array(record.salt));
  await putRecord({ ...record, ...encrypted });
  return next;
}
